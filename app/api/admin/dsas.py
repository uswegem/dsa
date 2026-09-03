"""
DSAs admin section.

DSAs otherwise only enter the system via Branch Manager uploads
(app/services/roster_sync.py). This lets an admin create one directly
(e.g. onboarding before their first sale) and edit branch/DTL assignment
without waiting for an upload.

A DTL reassignment here goes through the same effective-dated
dsa_dtl_assignments mechanism as an upload - see
app.services.roster_sync.sync_assignment - so it never overwrites a DSA's
supervision history, only closes the current open assignment and opens a
new one effective today.
"""
import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_permission
from app.models import Dsa, DsaDtlAssignment, Dtl, User
from app.schemas.common import DsaCreate, DsaOut, DsaUpdate
from app.services.audit import log_action
from app.services.roster_sync import sync_assignment

router = APIRouter(prefix="/dsas", dependencies=[Depends(require_permission("MANAGE_DSAS"))])


def _current_assignment(db: Session, dsa_id: int) -> DsaDtlAssignment | None:
    return (
        db.query(DsaDtlAssignment)
        .filter(DsaDtlAssignment.dsa_id == dsa_id, DsaDtlAssignment.effective_to.is_(None))
        .order_by(DsaDtlAssignment.effective_from.desc())
        .first()
    )


def _dsa_out(db: Session, dsa: Dsa) -> DsaOut:
    assignment = _current_assignment(db, dsa.id)
    return DsaOut(
        id=dsa.id, dsa_code=dsa.dsa_code, dsa_name=dsa.dsa_name, dsa_account_no=dsa.dsa_account_no,
        branch_id=dsa.branch_id,
        current_dtl_id=assignment.dtl_id if assignment else None,
        current_dtl_code=assignment.dtl.dtl_code if assignment else None,
        current_dtl_name=assignment.dtl.dtl_name if assignment else None,
    )


@router.get("", response_model=list[DsaOut])
def list_dsas(branch_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(Dsa)
    if branch_id is not None:
        q = q.filter(Dsa.branch_id == branch_id)
    return [_dsa_out(db, d) for d in q.order_by(Dsa.dsa_name).all()]


@router.post("", response_model=DsaOut)
def create_dsa(payload: DsaCreate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("MANAGE_DSAS"))):
    if db.query(Dsa).filter(Dsa.dsa_code == payload.dsa_code).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "A DSA with this code already exists")

    dtl = None
    if payload.dtl_id is not None:
        dtl = db.get(Dtl, payload.dtl_id)
        if dtl is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "dtl_id does not exist")

    dsa = Dsa(
        dsa_code=payload.dsa_code, dsa_name=payload.dsa_name,
        dsa_account_no=payload.dsa_account_no, branch_id=payload.branch_id,
    )
    db.add(dsa)
    db.flush()

    if dtl is not None:
        sync_assignment(db, dsa, dtl, dt.date.today())

    log_action(db, current_user.id, "DSA_CREATED", "Dsa", dsa.id, dsa_code=dsa.dsa_code, dtl_id=payload.dtl_id)
    db.commit()
    db.refresh(dsa)
    return _dsa_out(db, dsa)


@router.put("/{dsa_id}", response_model=DsaOut)
def update_dsa(dsa_id: int, payload: DsaUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("MANAGE_DSAS"))):
    dsa = db.get(Dsa, dsa_id)
    if dsa is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "DSA not found")

    changes = {}
    if payload.dsa_name is not None and payload.dsa_name != dsa.dsa_name:
        changes["dsa_name"] = {"old": dsa.dsa_name, "new": payload.dsa_name}
        dsa.dsa_name = payload.dsa_name
    if payload.dsa_account_no is not None and payload.dsa_account_no != dsa.dsa_account_no:
        changes["dsa_account_no"] = {"old": dsa.dsa_account_no, "new": payload.dsa_account_no}
        dsa.dsa_account_no = payload.dsa_account_no
    if payload.branch_id is not None and payload.branch_id != dsa.branch_id:
        changes["branch_id"] = {"old": dsa.branch_id, "new": payload.branch_id}
        dsa.branch_id = payload.branch_id

    if payload.dtl_id is not None:
        current = _current_assignment(db, dsa.id)
        if current is None or current.dtl_id != payload.dtl_id:
            dtl = db.get(Dtl, payload.dtl_id)
            if dtl is None:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "dtl_id does not exist")
            changes["dtl_id"] = {"old": current.dtl_id if current else None, "new": payload.dtl_id}
            sync_assignment(db, dsa, dtl, dt.date.today())

    db.flush()
    if changes:
        log_action(db, current_user.id, "DSA_UPDATED", "Dsa", dsa.id, changes=changes)
    db.commit()
    db.refresh(dsa)
    return _dsa_out(db, dsa)
