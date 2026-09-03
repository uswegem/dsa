"""
Matching / reconciliation between BranchSale (roster) rows and
BusinessTransaction (payout) rows for one upload pair.

Primary join key:   BranchSale.client_account_no == BusinessTransaction.client_disb_ext_account_no
Secondary check:    BranchSale.client_check_no   == BusinessTransaction.employee_no

Classification (per row, on both sides):
  MATCHED                     - both keys agree, exactly one candidate
  MATCHED_WITH_WARNING        - primary key matches, secondary check doesn't
  UNMATCHED_IN_BUSINESS_FILE  - branch manager reported a sale with no business txn
  UNMATCHED_IN_BRANCH_FILE    - business txn has no branch manager attribution
  DUPLICATE                   - more than one candidate match; tiebreak by
                                 closest disbursement date to the branch
                                 sale's loan_date within the reporting period

Only MATCHED / MATCHED_WITH_WARNING rows are eligible for commission
calculation. Everything else is surfaced in the exceptions view.
"""
import datetime as dt
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import BranchSale, BusinessTransaction, MatchedTransaction
from app.models.enums import MatchStatus


@dataclass
class MatchRunResult:
    matched: int = 0
    matched_with_warning: int = 0
    unmatched_in_business_file: int = 0
    unmatched_in_branch_file: int = 0
    duplicates: int = 0


def _commission_period(disbursement_date: dt.date) -> str:
    return f"{disbursement_date.year:04d}-{disbursement_date.month:02d}"


def run_matching(db: Session, branch_upload_id: int | None, business_upload_id: int | None) -> MatchRunResult:
    """Match BranchSale rows against BusinessTransaction rows.

    Matching is run pairwise across ALL not-yet-matched branch_sales and
    business_transactions (not scoped to a single upload pair) because the
    two files are uploaded independently and a branch sale from an earlier
    upload may only find its counterpart once a later business file lands
    (or vice versa). Rows already attached to a MatchedTransaction are left
    alone - re-running matching is safe to call after every new upload.
    """
    result = MatchRunResult()

    already_matched_branch_ids = {
        m.branch_sale_id for m in db.query(MatchedTransaction).filter(MatchedTransaction.branch_sale_id.isnot(None))
    }
    already_matched_biz_ids = {
        m.business_transaction_id
        for m in db.query(MatchedTransaction).filter(MatchedTransaction.business_transaction_id.isnot(None))
    }

    branch_sales = (
        db.query(BranchSale)
        .filter(~BranchSale.id.in_(already_matched_branch_ids) if already_matched_branch_ids else True)
        .all()
    )
    business_txns = (
        db.query(BusinessTransaction)
        .filter(~BusinessTransaction.id.in_(already_matched_biz_ids) if already_matched_biz_ids else True)
        .all()
    )

    # index business transactions by primary key (account number)
    biz_by_account: dict[str, list[BusinessTransaction]] = {}
    for bt in business_txns:
        biz_by_account.setdefault(bt.client_disb_ext_account_no, []).append(bt)

    consumed_biz_ids: set[int] = set()

    for bs in branch_sales:
        candidates = [bt for bt in biz_by_account.get(bs.client_account_no, []) if bt.id not in consumed_biz_ids]

        if not candidates:
            db.add(
                MatchedTransaction(
                    branch_sale_id=bs.id,
                    business_transaction_id=None,
                    match_status=MatchStatus.UNMATCHED_IN_BUSINESS_FILE,
                    match_notes=f"No Business Manager row with CLIENT_DISB_EXT_ACCOUNT_NO = {bs.client_account_no!r}",
                    commission_period=None,
                )
            )
            result.unmatched_in_business_file += 1
            continue

        if len(candidates) > 1:
            # DUPLICATE - tiebreak by closest disbursement date to the
            # branch sale's (informational) loan_date, falling back to the
            # first candidate if loan_date is unavailable.
            if bs.loan_date is not None:
                chosen = min(candidates, key=lambda bt: abs((bt.disbursement_date - bs.loan_date).days))
            else:
                chosen = candidates[0]
            other_ids = [c.id for c in candidates if c.id != chosen.id]
            db.add(
                MatchedTransaction(
                    branch_sale_id=bs.id,
                    business_transaction_id=chosen.id,
                    match_status=MatchStatus.DUPLICATE,
                    match_notes=(
                        f"{len(candidates)} Business Manager rows share CLIENT_DISB_EXT_ACCOUNT_NO = "
                        f"{bs.client_account_no!r} (business_transaction ids: {[c.id for c in candidates]}); "
                        f"tentatively paired with id={chosen.id} by closest disbursement date. "
                        "Needs manual resolution before this run is locked."
                    ),
                    commission_period=_commission_period(chosen.disbursement_date),
                )
            )
            consumed_biz_ids.add(chosen.id)
            for other_id in other_ids:
                pass  # the other candidates stay unconsumed; they'll surface via UNMATCHED_IN_BRANCH_FILE below
            result.duplicates += 1
            continue

        bt = candidates[0]
        consumed_biz_ids.add(bt.id)

        secondary_ok = (
            bs.client_check_no is not None
            and bt.employee_no is not None
            and bs.client_check_no.strip().upper() == bt.employee_no.strip().upper()
        )

        if secondary_ok:
            status = MatchStatus.MATCHED
            note = None
            result.matched += 1
        else:
            status = MatchStatus.MATCHED_WITH_WARNING
            note = (
                f"Primary key matched (CLIENT_ACCOUNT_NO = {bs.client_account_no!r}) but secondary check failed: "
                f"branch CLIENT_CHECK_NO={bs.client_check_no!r} vs business EMPLOYEE_NO={bt.employee_no!r}"
            )
            result.matched_with_warning += 1

        db.add(
            MatchedTransaction(
                branch_sale_id=bs.id,
                business_transaction_id=bt.id,
                match_status=status,
                match_notes=note,
                commission_period=_commission_period(bt.disbursement_date),
            )
        )

    # Any business transaction not consumed as a match/duplicate-winner has
    # no branch manager attribution.
    for bt in business_txns:
        if bt.id in consumed_biz_ids:
            continue
        db.add(
            MatchedTransaction(
                branch_sale_id=None,
                business_transaction_id=bt.id,
                match_status=MatchStatus.UNMATCHED_IN_BRANCH_FILE,
                match_notes=f"No Branch Manager row with CLIENT_ACCOUNT_NO = {bt.client_disb_ext_account_no!r}",
                commission_period=_commission_period(bt.disbursement_date),
            )
        )
        result.unmatched_in_branch_file += 1

    db.flush()
    return result
