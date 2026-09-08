from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_permission
from app.models import Dtl, User
from app.schemas.common import BulkUpdateResultOut, DtlCreate, DtlOut, DtlUpdate
from app.services.audit import log_action
from app.services.branch_lookup import get_required_branch
from app.services.bulk_details import apply_bulk_update, parse_bulk_detail_file

router = APIRouter(prefix="/dtls", dependencies=[Depends(require_permission("MANAGE_DTLS"))])


@router.post("", response_model=DtlOut)
def create_dtl(payload: DtlCreate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("MANAGE_DTLS"))):
    if db.query(Dtl).filter(Dtl.dtl_code == payload.dtl_code).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "DTL with this code already exists")
    get_required_branch(db, payload.branch_id)
    dtl = Dtl(
        dtl_code=payload.dtl_code, dtl_name=payload.dtl_name,
        dtl_account_no=payload.dtl_account_no, branch_id=payload.branch_id,
    )
    db.add(dtl)
    db.flush()
    log_action(db, current_user.id, "DTL_CREATED", "Dtl", dtl.id, dtl_code=dtl.dtl_code)
    db.commit()
    db.refresh(dtl)
    return dtl


@router.get("", response_model=list[DtlOut])
def list_dtls(branch_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(Dtl)
    if branch_id is not None:
        q = q.filter(Dtl.branch_id == branch_id)
    return q.order_by(Dtl.dtl_name).all()


@router.put("/{dtl_id}", response_model=DtlOut)
def update_dtl(dtl_id: int, payload: DtlUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("MANAGE_DTLS"))):
    dtl = db.get(Dtl, dtl_id)
    if dtl is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "DTL not found")

    changes = {}
    if payload.dtl_name is not None and payload.dtl_name != dtl.dtl_name:
        changes["dtl_name"] = {"old": dtl.dtl_name, "new": payload.dtl_name}
        dtl.dtl_name = payload.dtl_name
    if payload.dtl_account_no is not None and payload.dtl_account_no != dtl.dtl_account_no:
        changes["dtl_account_no"] = {"old": dtl.dtl_account_no, "new": payload.dtl_account_no}
        dtl.dtl_account_no = payload.dtl_account_no
    if payload.branch_id is not None and payload.branch_id != dtl.branch_id:
        get_required_branch(db, payload.branch_id)
        changes["branch_id"] = {"old": dtl.branch_id, "new": payload.branch_id}
        dtl.branch_id = payload.branch_id

    db.flush()
    if changes:
        log_action(db, current_user.id, "DTL_UPDATED", "Dtl", dtl.id, changes=changes)
    db.commit()
    db.refresh(dtl)
    return dtl


@router.post("/bulk-update", response_model=BulkUpdateResultOut)
async def bulk_update_dtls(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("MANAGE_DTLS")),
):
    """Corrects dtl_code/dtl_account_no on EXISTING DTLs in bulk from a
    CSV/Excel file (columns: DTL_NAME, BRANCH, DTL_CODE, DTL_ACCOUNT_NO).
    Matches each row by (DTL_NAME, BRANCH) - case-insensitive, trimmed -
    never creates a new DTL; an unmatched row is reported back, not
    silently dropped or auto-created. See app/services/bulk_details.py.
    """
    contents = await file.read()
    try:
        parsed = parse_bulk_detail_file(contents, file.filename, "dtl")
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

    summary = apply_bulk_update(
        db, parsed,
        model=Dtl, name_field="dtl_name", code_field="dtl_code", account_field="dtl_account_no",
        entity_label="DTL", entity_type_for_audit="Dtl", log_action_name="DTL_BULK_UPDATED",
        current_user_id=current_user.id,
    )
    db.commit()
    return BulkUpdateResultOut.from_summary(summary)
