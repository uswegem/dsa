from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.deps import require_permission
from app.core.security import hash_password
from app.models import Role, User
from app.schemas.auth import UserCreate, UserOut
from app.services.audit import log_action

router = APIRouter(prefix="/users", dependencies=[Depends(require_permission("MANAGE_USERS"))])


@router.post("", response_model=UserOut)
def create_user(payload: UserCreate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("MANAGE_USERS"))):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with this email already exists")
    role = db.get(Role, payload.role_id)
    if role is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "role_id does not exist")
    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role_id=payload.role_id,
        branch_id=payload.branch_id,
    )
    db.add(user)
    db.flush()
    log_action(db, current_user.id, "USER_CREATED", "User", user.id, role=role.name)
    db.commit()
    db.refresh(user)
    return UserOut.from_user(user)


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)):
    users = db.query(User).options(joinedload(User.role).joinedload(Role.permissions)).order_by(User.email).all()
    return [UserOut.from_user(u) for u in users]
