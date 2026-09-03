from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_any
from app.models import CommissionRun, User
from app.models.enums import UserRole
from app.reports.excel import generate_commission_report, generate_exceptions_only_report

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _resolve_branch_scope(current_user: User, requested_branch_id: int | None) -> int | None:
    if current_user.role == UserRole.BRANCH_MANAGER:
        return current_user.branch_id  # branch managers never get an org-wide export
    return requested_branch_id  # None = consolidated, all branches


@router.get("/commission/{run_id}")
def download_commission_report(
    run_id: int,
    branch_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any),
):
    run = db.get(CommissionRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    if current_user.role == UserRole.BRANCH_MANAGER and run.branch_id not in (None, current_user.branch_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted for this branch's report")

    scoped_branch_id = _resolve_branch_scope(current_user, branch_id)
    buf = generate_commission_report(db, run, branch_id=scoped_branch_id)

    scope_label = f"branch{scoped_branch_id}" if scoped_branch_id else "consolidated"
    filename = f"commission_{run.period}_{scope_label}_run{run.id}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/exceptions")
def download_exceptions_report(
    period: str,
    branch_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any),
):
    scoped_branch_id = _resolve_branch_scope(current_user, branch_id)
    buf = generate_exceptions_only_report(db, period=period, branch_id=scoped_branch_id)

    scope_label = f"branch{scoped_branch_id}" if scoped_branch_id else "consolidated"
    filename = f"exceptions_{period}_{scope_label}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
