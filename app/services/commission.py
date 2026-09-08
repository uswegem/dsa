"""
Commission calculation engine.

Rules (per calendar month, bucketed by the Business Manager file's
Disbursement date - see MatchedTransaction.commission_period):
  DSA: 7% of gross sales for New Loans (NL), 3% of net sales for Top-ups (RF)
  DTL: 1% of gross sales for New Loans, 1% of net sales for Top-ups,
       for the DSAs under their supervision

DSA-only deduction: WHT (Withholding Tax, Settings.dsa_wht_rate = 5%) is
deducted from each DSA CommissionLine's commission_amount, stored alongside
it as wht_amount/net_commission_amount - net_commission_amount is the
actual payable figure. DTL commission is never WHT-deducted. SDL/WCF are
statutory REPORTING figures only (never deducted) - computed in the DSA
Summary report, not stored per line - see app/reports/excel.py.

Gross = Business Manager Disbursement Amt (NL rows).
Net   = configurable basis, currently Business Manager Appl Amount minus
        Letshego Topup (RF rows) - see Settings.net_topup_minuend_field /
        net_topup_subtrahend_field and get_topup_net_base().

Only MATCHED and MATCHED_WITH_WARNING transactions are eligible. A
non-positive (zero or negative) net base is never used silently - see
get_topup_net_base()'s callers: calculate_commission_run() excludes such a
transaction from commission, and app/services/exceptions.py surfaces it in
the exceptions view (INVALID_TOPUP_BASE) until the underlying data is
corrected.

A LOCKED run's commission_lines are never mutated - see lock_run(). A
formula change here (like the appl_amount/letshego_topup switch above)
never retroactively recalculates an already-LOCKED run; only its own
already-DRAFT runs, and any new run, pick it up.
"""
import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    BranchSale,
    BusinessTransaction,
    CommissionLine,
    CommissionRun,
    Dsa,
    DsaDtlAssignment,
    Dtl,
    MatchedTransaction,
)
from app.models.enums import CommissionBase, LoanType, MatchStatus, PayeeType, RunStatus, RunType

settings = get_settings()

ELIGIBLE_STATUSES = (MatchStatus.MATCHED, MatchStatus.MATCHED_WITH_WARNING)


class CommissionRunError(Exception):
    pass


def get_topup_net_base(bt: BusinessTransaction) -> float | None:
    """The single place that defines what 'net' means for a top-up (RF).

    Currently: Appl Amount minus Letshego Topup (see
    Settings.net_topup_minuend_field/net_topup_subtrahend_field docstring
    for why, and what to change if the definition changes again).

    Returns None if either component is missing (can't compute). Returning
    a non-positive number is deliberate - callers decide what to do with
    it (calculate_commission_run excludes it from commission;
    app/services/exceptions.py surfaces it as INVALID_TOPUP_BASE) rather
    than this function silently hiding a bad value.
    """
    minuend = getattr(bt, settings.net_topup_minuend_field)
    subtrahend = getattr(bt, settings.net_topup_subtrahend_field)
    if minuend is None or subtrahend is None:
        return None
    return float(minuend) - float(subtrahend)


def _find_dtl_for_transaction(db: Session, bs: BranchSale, dsa: Dsa, on_date: dt.date) -> Dtl | None:
    """Prefer the DTL recorded directly on this branch sale row (the most
    precise, per-transaction signal). Fall back to the effective-dated
    dsa_dtl_assignments history if the row didn't carry one.
    """
    if bs.dtl_code:
        dtl = db.query(Dtl).filter(Dtl.dtl_code == bs.dtl_code).first()
        if dtl is not None:
            return dtl

    assignment = (
        db.query(DsaDtlAssignment)
        .filter(
            DsaDtlAssignment.dsa_id == dsa.id,
            DsaDtlAssignment.effective_from <= on_date,
            (DsaDtlAssignment.effective_to.is_(None)) | (DsaDtlAssignment.effective_to >= on_date),
        )
        .order_by(DsaDtlAssignment.effective_from.desc())
        .first()
    )
    return assignment.dtl if assignment else None


@dataclass
class CalculationResult:
    lines_created: int = 0
    skipped_no_dsa: int = 0
    skipped_no_dtl: int = 0
    skipped_zero_or_missing_base: int = 0
    skipped_already_paid_elsewhere: list[int] = field(default_factory=list)


def calculate_commission_run(db: Session, run: CommissionRun) -> CalculationResult:
    """(Re)computes commission_lines for a DRAFT run. Safe to call repeatedly
    while the run is still DRAFT - existing lines for this run are replaced.
    """
    if run.status != RunStatus.DRAFT:
        raise CommissionRunError(f"Cannot calculate a run in status {run.status.value}; only DRAFT runs can be (re)calculated.")

    # Wipe and recompute this run's own lines (idempotent while DRAFT).
    db.query(CommissionLine).filter(CommissionLine.commission_run_id == run.id).delete()

    # Never double-pay a transaction that already has a line in some OTHER
    # run (whatever that run's scope or status), whether this is a
    # branch-scoped run or an org-wide one.
    already_paid_matched_ids = {
        row[0]
        for row in db.query(CommissionLine.matched_transaction_id)
        .filter(CommissionLine.commission_run_id != run.id)
        .distinct()
    }

    query = (
        db.query(MatchedTransaction)
        .join(BusinessTransaction, MatchedTransaction.business_transaction_id == BusinessTransaction.id)
        .join(BranchSale, MatchedTransaction.branch_sale_id == BranchSale.id)
        .filter(
            MatchedTransaction.commission_period == run.period,
            MatchedTransaction.match_status.in_(ELIGIBLE_STATUSES),
        )
    )
    if run.run_type == RunType.BRANCH:
        if run.branch_id is None:
            raise CommissionRunError("BRANCH run must have a branch_id")
        query = query.filter(BranchSale.branch_id == run.branch_id)

    result = CalculationResult()

    for mt in query.all():
        if mt.id in already_paid_matched_ids:
            result.skipped_already_paid_elsewhere.append(mt.id)
            continue

        bs = mt.branch_sale
        bt = mt.business_transaction

        dsa = db.query(Dsa).filter(Dsa.dsa_code == bs.dsa_code).first()
        if dsa is None:
            result.skipped_no_dsa += 1
            continue

        loan_type = LoanType(bt.loan_type)
        if loan_type == LoanType.NL:
            base_used = CommissionBase.GROSS
            base_amount = bt.disbursement_amt
            dsa_rate = settings.dsa_nl_rate
            dtl_rate = settings.dtl_nl_rate
        else:
            base_used = CommissionBase.NET
            base_amount = get_topup_net_base(bt)
            dsa_rate = settings.dsa_rf_rate
            dtl_rate = settings.dtl_rf_rate

        if base_amount is None or float(base_amount) <= 0:
            result.skipped_zero_or_missing_base += 1
            continue

        base_amount = float(base_amount)

        dsa_commission_amount = round(base_amount * dsa_rate, 2)
        # WHT is deducted for DSAs only - see Settings.dsa_wht_rate. DTL
        # commission below is untouched: no WHT, no wht_amount/
        # net_commission_amount set.
        dsa_wht_amount = round(dsa_commission_amount * settings.dsa_wht_rate, 2)
        db.add(
            CommissionLine(
                commission_run_id=run.id,
                matched_transaction_id=mt.id,
                payee_type=PayeeType.DSA,
                dsa_id=dsa.id,
                dtl_id=None,
                loan_type=loan_type,
                base_used=base_used,
                base_amount=base_amount,
                rate=dsa_rate,
                commission_amount=dsa_commission_amount,
                wht_amount=dsa_wht_amount,
                net_commission_amount=round(dsa_commission_amount - dsa_wht_amount, 2),
            )
        )
        result.lines_created += 1

        dtl = _find_dtl_for_transaction(db, bs, dsa, bt.disbursement_date)
        if dtl is None:
            result.skipped_no_dtl += 1
        else:
            db.add(
                CommissionLine(
                    commission_run_id=run.id,
                    matched_transaction_id=mt.id,
                    payee_type=PayeeType.DTL,
                    dsa_id=None,
                    dtl_id=dtl.id,
                    loan_type=loan_type,
                    base_used=base_used,
                    base_amount=base_amount,
                    rate=dtl_rate,
                    commission_amount=round(base_amount * dtl_rate, 2),
                )
            )
            result.lines_created += 1

    db.flush()
    return result


def review_run(db: Session, run: CommissionRun, reviewer_user_id: int) -> CommissionRun:
    if run.status != RunStatus.DRAFT:
        raise CommissionRunError(f"Cannot review a run in status {run.status.value}")
    run.status = RunStatus.REVIEWED
    run.reviewed_by_user_id = reviewer_user_id
    run.reviewed_at = dt.datetime.now(dt.timezone.utc)
    db.flush()
    return run


def lock_run(db: Session, run: CommissionRun, locker_user_id: int) -> CommissionRun:
    """Locks the run. From this point on its commission_lines must never be
    mutated - corrections go through commission_adjustments on a later run.
    """
    if run.status != RunStatus.REVIEWED:
        raise CommissionRunError(f"Cannot lock a run in status {run.status.value}; it must be REVIEWED first.")
    run.status = RunStatus.LOCKED
    run.locked_by_user_id = locker_user_id
    run.locked_at = dt.datetime.now(dt.timezone.utc)
    db.flush()
    return run


def mark_paid(db: Session, run: CommissionRun) -> CommissionRun:
    if run.status != RunStatus.LOCKED:
        raise CommissionRunError(f"Cannot mark a run PAID from status {run.status.value}; it must be LOCKED first.")
    run.status = RunStatus.PAID
    run.paid_at = dt.datetime.now(dt.timezone.utc)
    db.flush()
    return run
