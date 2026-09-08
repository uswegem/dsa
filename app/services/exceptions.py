"""
Exceptions: rows that must be visible/reviewed before a commission run is
finalized, but don't block anything else. Two sources, merged here so the
JSON endpoint (app/api/exceptions_view.py) and the Excel report
(app/reports/excel.py) share one definition instead of drifting apart:

  1. Persisted match-quality categories on MatchedTransaction.match_status
     (UNMATCHED_*, DUPLICATE, MATCHED_WITH_WARNING) - set by run_matching().
  2. Dynamically-detected business-rule problems on an otherwise-resolved
     match - currently just an invalid top-up commission base. This is
     computed fresh every call, never stored on the row, so a later upload
     correcting the underlying Appl Amount / Letshego Topup figures clears
     the flag automatically, exactly like UNMATCHED_* re-resolves itself
     when the missing side of a match shows up later.
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import BusinessTransaction, MatchedTransaction
from app.models.enums import LoanType, MatchStatus
from app.services.commission import ELIGIBLE_STATUSES, get_topup_net_base

STORED_EXCEPTION_STATUSES = [
    MatchStatus.UNMATCHED_IN_BUSINESS_FILE,
    MatchStatus.UNMATCHED_IN_BRANCH_FILE,
    MatchStatus.DUPLICATE,
    MatchStatus.MATCHED_WITH_WARNING,
]

INVALID_TOPUP_BASE = "INVALID_TOPUP_BASE"

EXCEPTION_CATEGORY_LABELS = {
    MatchStatus.UNMATCHED_IN_BUSINESS_FILE.value: "Unmatched - in Branch Manager file only (no Business Manager transaction)",
    MatchStatus.UNMATCHED_IN_BRANCH_FILE.value: "Unmatched - in Business Manager file only (no DSA/DTL attribution)",
    MatchStatus.DUPLICATE.value: "Duplicate - multiple Business Manager candidates for one Branch Manager row",
    MatchStatus.MATCHED_WITH_WARNING.value: "Matched with warning - secondary check (CLIENT_CHECK_NO vs EMPLOYEE_NO) failed",
    INVALID_TOPUP_BASE: "Invalid top-up commission base - Appl Amount minus Letshego Topup is zero, negative, or missing",
}


@dataclass
class ExceptionEntry:
    matched_transaction: MatchedTransaction
    category: str  # a MatchStatus value, or INVALID_TOPUP_BASE
    note: str | None


def _invalid_topup_base_note(bt: BusinessTransaction, base: float | None) -> str:
    appl = f"{float(bt.appl_amount):,.2f}" if bt.appl_amount is not None else "(missing)"
    topup = f"{float(bt.letshego_topup):,.2f}" if bt.letshego_topup is not None else "(missing)"
    base_desc = f"{base:,.2f}" if base is not None else "unavailable (a component is missing)"
    return (
        f"Top-up net base = Appl Amount ({appl}) - Letshego Topup ({topup}) = {base_desc}. "
        "This must be positive to generate commission - excluded until reviewed and the source data is corrected."
    )


def find_exceptions(db: Session) -> list[ExceptionEntry]:
    """All current exceptions, org-wide, freshly computed - callers (the
    JSON endpoint, the Excel report) filter by branch/period themselves,
    same pattern as everywhere else in the app."""
    entries: dict[int, ExceptionEntry] = {}

    for mt in db.query(MatchedTransaction).filter(MatchedTransaction.match_status.in_(STORED_EXCEPTION_STATUSES)).all():
        entries[mt.id] = ExceptionEntry(matched_transaction=mt, category=mt.match_status.value, note=mt.match_notes)

    invalid_base_q = (
        db.query(MatchedTransaction)
        .join(BusinessTransaction, MatchedTransaction.business_transaction_id == BusinessTransaction.id)
        .filter(MatchedTransaction.match_status.in_(ELIGIBLE_STATUSES), BusinessTransaction.loan_type == LoanType.RF)
    )
    for mt in invalid_base_q.all():
        bt = mt.business_transaction
        base = get_topup_net_base(bt)
        if base is not None and base > 0:
            continue
        # An invalid base is the more actionable/blocking problem - it
        # takes over the slot even if this row also has a plain
        # match-quality warning (that context isn't lost, just deprioritized
        # relative to "this can't generate commission at all yet").
        entries[mt.id] = ExceptionEntry(
            matched_transaction=mt, category=INVALID_TOPUP_BASE, note=_invalid_topup_base_note(bt, base)
        )

    return list(entries.values())
