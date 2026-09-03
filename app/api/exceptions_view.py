from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_any
from app.models import MatchedTransaction, User
from app.models.enums import MatchStatus, UserRole
from app.schemas.commission import ExceptionRow

router = APIRouter(prefix="/api/exceptions", tags=["exceptions"])

EXCEPTION_STATUSES = [
    MatchStatus.UNMATCHED_IN_BUSINESS_FILE,
    MatchStatus.UNMATCHED_IN_BRANCH_FILE,
    MatchStatus.DUPLICATE,
    MatchStatus.MATCHED_WITH_WARNING,
]


@router.get("", response_model=list[ExceptionRow])
def list_exceptions(
    period: str | None = None,
    branch_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any),
):
    if current_user.role == UserRole.BRANCH_MANAGER:
        branch_id = current_user.branch_id  # forced scope, can't be widened by query param

    q = db.query(MatchedTransaction).filter(MatchedTransaction.match_status.in_(EXCEPTION_STATUSES))
    rows = q.all()

    out: list[ExceptionRow] = []
    for mt in rows:
        bs = mt.branch_sale
        bt = mt.business_transaction

        row_branch_id = bs.branch_id if bs else None
        if branch_id is not None and row_branch_id != branch_id:
            continue
        row_period = mt.commission_period or (bs.loan_date.strftime("%Y-%m") if bs and bs.loan_date else None)
        if period is not None and row_period != period:
            continue

        out.append(
            ExceptionRow(
                match_status=mt.match_status.value,
                branch_name=bs.branch.name if bs and bs.branch else None,
                client_name=bs.client_name if bs else None,
                client_account_no_branch=bs.client_account_no if bs else None,
                client_account_no_business=bt.client_disb_ext_account_no if bt else None,
                dsa_code=bs.dsa_code if bs else None,
                dsa_name=bs.dsa_name if bs else None,
                loan_type=bt.loan_type.value if bt else None,
                disbursement_date=bt.disbursement_date.isoformat() if bt else None,
                notes=mt.match_notes,
            )
        )
    return out
