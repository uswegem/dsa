from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_permission
from app.models import Dtl, User
from app.schemas.common import DtlCreate, DtlOut, DtlUpdate
from app.services.audit import log_action

router = APIRouter(prefix="/dtls", dependencies=[Depends(require_permission("MANAGE_DTLS"))])


@router.post("", response_model=DtlOut)
def create_dtl(payload: DtlCreate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("MANAGE_DTLS"))):
    if db.query(Dtl).filter(Dtl.dtl_code == payload.dtl_code).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "DTL with this code already exists")
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
        changes["branch_id"] = {"old": dtl.branch_id, "new": payload.branch_id}
        dtl.branch_id = payload.branch_id

    db.flush()
    if changes:
        log_action(db, current_user.id, "DTL_UPDATED", "Dtl", dtl.id, changes=changes)
    db.commit()
    db.refresh(dtl)
    return dtl
