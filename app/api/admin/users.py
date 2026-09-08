from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.deps import require_permission
from app.core.security import hash_password
from app.models import Role, User
from app.schemas.auth import UserCreate, UserOut, UserUpdate
from app.services.audit import log_action
from app.services.branch_lookup import get_head_office_branch, get_required_branch

router = APIRouter(prefix="/users", dependencies=[Depends(require_permission("MANAGE_USERS"))])

BRANCH_MANAGER_ROLE = "BRANCH_MANAGER"
BUSINESS_MANAGER_ROLE = "BUSINESS_MANAGER"


def _resolve_branch_for_role(db: Session, role: Role, requested_branch_id: int | None, existing_branch_id: int | None = None) -> int | None:
    """Applies the branch policy for a role, used on both create and edit:

    - BUSINESS_MANAGER is always pinned to Head Office, ignoring whatever
      branch_id was requested - it's a fixed record for this role, not an
      editable choice, so an admin can't accidentally move them to another
      branch. This doesn't touch their permissions/data scope: they still
      hold VIEW_ALL_* (see ROLE_SEED), which is checked independently of
      branch_id everywhere reports/exceptions/uploads use it.
    - BRANCH_MANAGER must end up with exactly one specific branch: the
      requested one if given, else whatever they already had - but never
      none, and it must reference a real branch.
    - Every other role (ADMIN, custom roles) keeps requested_branch_id if
      provided, else existing_branch_id unchanged - branch stays optional
      for org-wide roles.
    """
    if role.name == BUSINESS_MANAGER_ROLE:
        return get_head_office_branch(db).id
    if role.name == BRANCH_MANAGER_ROLE:
        branch_id = requested_branch_id if requested_branch_id is not None else existing_branch_id
        return get_required_branch(db, branch_id, "branch_id").id
    return requested_branch_id if requested_branch_id is not None else existing_branch_id


@router.post("", response_model=UserOut)
def create_user(payload: UserCreate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("MANAGE_USERS"))):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with this email already exists")
    role = db.get(Role, payload.role_id)
    if role is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "role_id does not exist")

    branch_id = _resolve_branch_for_role(db, role, payload.branch_id)

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role_id=payload.role_id,
        branch_id=branch_id,
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


@router.put("/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("MANAGE_USERS"))):
    user = db.query(User).options(joinedload(User.role)).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    changes = {}

    if payload.full_name is not None and payload.full_name != user.full_name:
        changes["full_name"] = {"old": user.full_name, "new": payload.full_name}
        user.full_name = payload.full_name

    role = user.role
    if payload.role_id is not None and payload.role_id != user.role_id:
        role = db.get(Role, payload.role_id)
        if role is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "role_id does not exist")
        changes["role_id"] = {"old": user.role_id, "new": payload.role_id}
        user.role_id = payload.role_id

    # Re-derive branch on every save (not just when role/branch_id changed) -
    # this is what keeps a BUSINESS_MANAGER pinned to Head Office even if an
    # admin edits some other field on their record, and re-validates a
    # BRANCH_MANAGER's existing branch still exists.
    new_branch_id = _resolve_branch_for_role(db, role, payload.branch_id, user.branch_id)
    if new_branch_id != user.branch_id:
        changes["branch_id"] = {"old": user.branch_id, "new": new_branch_id}
        user.branch_id = new_branch_id

    if payload.is_active is not None and payload.is_active != user.is_active:
        changes["is_active"] = {"old": user.is_active, "new": payload.is_active}
        user.is_active = payload.is_active

    if payload.password:
        user.hashed_password = hash_password(payload.password)
        changes["password"] = "reset"

    db.flush()
    if changes:
        log_action(db, current_user.id, "USER_UPDATED", "User", user.id, changes=changes)
    db.commit()
    db.refresh(user)
    return UserOut.from_user(user)
