from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_any_permission
from app.models import CommissionRun, User
from app.reports.excel import generate_commission_report, generate_exceptions_only_report
from app.services.permissions import user_has_permission

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _resolve_branch_scope(current_user: User, requested_branch_id: int | None, all_permission: str) -> int | None:
    if not user_has_permission(current_user, all_permission):
        return current_user.branch_id  # never gets an org-wide export without the ALL permission
    return requested_branch_id  # None = consolidated, all branches


@router.get("/commission/{run_id}")
def download_commission_report(
    run_id: int,
    branch_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("VIEW_ALL_REPORTS", "VIEW_OWN_BRANCH_REPORTS")),
):
    run = db.get(CommissionRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    if not user_has_permission(current_user, "VIEW_ALL_REPORTS") and run.branch_id not in (None, current_user.branch_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted for this branch's report")

    scoped_branch_id = _resolve_branch_scope(current_user, branch_id, "VIEW_ALL_REPORTS")
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
    current_user: User = Depends(require_any_permission("VIEW_ALL_EXCEPTIONS", "VIEW_OWN_BRANCH_EXCEPTIONS")),
):
    scoped_branch_id = _resolve_branch_scope(current_user, branch_id, "VIEW_ALL_EXCEPTIONS")
    buf = generate_exceptions_only_report(db, period=period, branch_id=scoped_branch_id)

    scope_label = f"branch{scoped_branch_id}" if scoped_branch_id else "consolidated"
    filename = f"exceptions_{period}_{scope_label}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
