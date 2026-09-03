from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_permission
from app.models import Branch
from app.schemas.common import BranchCreate, BranchOut

router = APIRouter(prefix="/branches", dependencies=[Depends(require_permission("MANAGE_BRANCHES"))])


@router.post("", response_model=BranchOut)
def create_branch(payload: BranchCreate, db: Session = Depends(get_db)):
    if db.query(Branch).filter(Branch.name == payload.name).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Branch with this name already exists")
    branch = Branch(name=payload.name, code=payload.code)
    db.add(branch)
    db.commit()
    db.refresh(branch)
    return branch


@router.get("", response_model=list[BranchOut])
def list_branches(db: Session = Depends(get_db)):
    return db.query(Branch).order_by(Branch.name).all()
