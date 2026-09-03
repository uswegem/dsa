from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_permission
from app.models import Dtl
from app.schemas.common import DtlCreate, DtlOut

router = APIRouter(prefix="/dtls", dependencies=[Depends(require_permission("MANAGE_DTLS"))])


@router.post("", response_model=DtlOut)
def create_dtl(payload: DtlCreate, db: Session = Depends(get_db)):
    if db.query(Dtl).filter(Dtl.dtl_code == payload.dtl_code).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "DTL with this code already exists")
    dtl = Dtl(dtl_code=payload.dtl_code, dtl_name=payload.dtl_name, branch_id=payload.branch_id)
    db.add(dtl)
    db.commit()
    db.refresh(dtl)
    return dtl


@router.get("", response_model=list[DtlOut])
def list_dtls(branch_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(Dtl)
    if branch_id is not None:
        q = q.filter(Dtl.branch_id == branch_id)
    return q.order_by(Dtl.dtl_name).all()
