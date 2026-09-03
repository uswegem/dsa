from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_admin
from app.core.security import hash_password
from app.models import Branch, Dsa, Dtl, User
from app.schemas.auth import UserCreate, UserOut
from app.schemas.common import BranchCreate, BranchOut, DsaOut, DtlCreate, DtlOut
from app.services.audit import log_action

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.post("/branches", response_model=BranchOut)
def create_branch(payload: BranchCreate, db: Session = Depends(get_db)):
    if db.query(Branch).filter(Branch.name == payload.name).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Branch with this name already exists")
    branch = Branch(name=payload.name, code=payload.code)
    db.add(branch)
    db.commit()
    db.refresh(branch)
    return branch


@router.get("/branches", response_model=list[BranchOut])
def list_branches(db: Session = Depends(get_db)):
    return db.query(Branch).order_by(Branch.name).all()


@router.post("/dtls", response_model=DtlOut)
def create_dtl(payload: DtlCreate, db: Session = Depends(get_db)):
    if db.query(Dtl).filter(Dtl.dtl_code == payload.dtl_code).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "DTL with this code already exists")
    dtl = Dtl(dtl_code=payload.dtl_code, dtl_name=payload.dtl_name, branch_id=payload.branch_id)
    db.add(dtl)
    db.commit()
    db.refresh(dtl)
    return dtl


@router.get("/dtls", response_model=list[DtlOut])
def list_dtls(branch_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(Dtl)
    if branch_id is not None:
        q = q.filter(Dtl.branch_id == branch_id)
    return q.order_by(Dtl.dtl_name).all()


@router.get("/dsas", response_model=list[DsaOut])
def list_dsas(branch_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(Dsa)
    if branch_id is not None:
        q = q.filter(Dsa.branch_id == branch_id)
    return q.order_by(Dsa.dsa_name).all()


@router.post("/users", response_model=UserOut)
def create_user(payload: UserCreate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with this email already exists")
    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
        branch_id=payload.branch_id,
    )
    db.add(user)
    db.flush()
    log_action(db, current_user.id, "USER_CREATED", "User", user.id, role=payload.role.value)
    db.commit()
    db.refresh(user)
    return user


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.query(User).order_by(User.email).all()
