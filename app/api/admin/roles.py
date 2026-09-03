"""
Roles admin section: create/edit/delete roles and assign permissions.

Two safety guards, per the RBAC design:
  - is_system_role roles (ADMIN, BRANCH_MANAGER, BUSINESS_MANAGER) can have
    their permissions edited, but never deleted - the app's baseline
    assumptions depend on them existing.
  - No edit/delete may leave the system with zero active users holding
    MANAGE_ROLES - see _would_lose_all_manage_roles_access() - so an admin
    can never accidentally lock everyone out of role management.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.deps import require_permission
from app.models import Permission, Role, User
from app.models.rbac import role_permissions
from app.schemas.common import PermissionOut, RoleCreate, RoleOut, RoleUpdate
from app.services.audit import log_action

router = APIRouter(prefix="", dependencies=[Depends(require_permission("MANAGE_ROLES"))])

MANAGE_ROLES_KEY = "MANAGE_ROLES"


def _role_out(role: Role) -> RoleOut:
    keys = sorted(p.key for p in role.permissions)
    return RoleOut(
        id=role.id, name=role.name, description=role.description, is_system_role=role.is_system_role,
        permission_count=len(keys), permissions=keys,
    )


def _would_lose_all_manage_roles_access(db: Session, role_id_being_edited: int | None, new_permission_keys: set[str]) -> bool:
    """True if, after applying new_permission_keys to the role identified by
    role_id_being_edited (None = a role being deleted / doesn't matter),
    no active user anywhere would still hold MANAGE_ROLES."""
    if MANAGE_ROLES_KEY in new_permission_keys:
        return False  # this role keeps it - always safe

    other_role_ids_with_manage_roles = (
        db.query(Role.id)
        .join(role_permissions, role_permissions.c.role_id == Role.id)
        .join(Permission, Permission.id == role_permissions.c.permission_id)
        .filter(Permission.key == MANAGE_ROLES_KEY, Role.id != role_id_being_edited)
        .subquery()
    )
    active_holder_count = (
        db.query(User)
        .filter(User.role_id.in_(db.query(other_role_ids_with_manage_roles.c.id)), User.is_active.is_(True))
        .count()
    )
    return active_holder_count == 0


@router.get("/permissions", response_model=list[PermissionOut])
def list_permissions(db: Session = Depends(get_db)):
    return db.query(Permission).order_by(Permission.key).all()


@router.get("/roles", response_model=list[RoleOut])
def list_roles(db: Session = Depends(get_db)):
    roles = db.query(Role).options(joinedload(Role.permissions)).order_by(Role.name).all()
    return [_role_out(r) for r in roles]


@router.get("/roles/{role_id}", response_model=RoleOut)
def get_role(role_id: int, db: Session = Depends(get_db)):
    role = db.query(Role).options(joinedload(Role.permissions)).filter(Role.id == role_id).first()
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")
    return _role_out(role)


@router.post("/roles", response_model=RoleOut)
def create_role(payload: RoleCreate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("MANAGE_ROLES"))):
    if db.query(Role).filter(Role.name == payload.name).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "A role with this name already exists")

    unknown = set(payload.permission_keys) - {p.key for p in db.query(Permission).all()}
    if unknown:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown permission key(s): {sorted(unknown)}")

    role = Role(name=payload.name, description=payload.description, is_system_role=False)
    if payload.permission_keys:
        role.permissions = db.query(Permission).filter(Permission.key.in_(payload.permission_keys)).all()
    db.add(role)
    db.flush()
    log_action(db, current_user.id, "ROLE_CREATED", "Role", role.id, name=role.name, permissions=payload.permission_keys)
    db.commit()
    db.refresh(role)
    return _role_out(role)


@router.put("/roles/{role_id}", response_model=RoleOut)
def update_role(role_id: int, payload: RoleUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("MANAGE_ROLES"))):
    role = db.query(Role).options(joinedload(Role.permissions)).filter(Role.id == role_id).first()
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")

    changes = {}

    if payload.name is not None and payload.name != role.name:
        if db.query(Role).filter(Role.name == payload.name, Role.id != role_id).first():
            raise HTTPException(status.HTTP_409_CONFLICT, "A role with this name already exists")
        changes["name"] = {"old": role.name, "new": payload.name}
        role.name = payload.name

    if payload.description is not None and payload.description != role.description:
        changes["description"] = {"old": role.description, "new": payload.description}
        role.description = payload.description

    if payload.permission_keys is not None:
        unknown = set(payload.permission_keys) - {p.key for p in db.query(Permission).all()}
        if unknown:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown permission key(s): {sorted(unknown)}")
        new_keys = set(payload.permission_keys)
        if _would_lose_all_manage_roles_access(db, role_id, new_keys):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Refusing to save: this would leave no active user with MANAGE_ROLES, locking everyone out of role management.",
            )
        old_keys = sorted(p.key for p in role.permissions)
        role.permissions = db.query(Permission).filter(Permission.key.in_(payload.permission_keys)).all()
        changes["permissions"] = {"old": old_keys, "new": sorted(new_keys)}

    db.flush()
    if changes:
        log_action(db, current_user.id, "ROLE_UPDATED", "Role", role.id, changes=changes)
    db.commit()
    db.refresh(role)
    return _role_out(role)


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(role_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("MANAGE_ROLES"))):
    role = db.query(Role).options(joinedload(Role.permissions)).filter(Role.id == role_id).first()
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")
    if role.is_system_role:
        raise HTTPException(status.HTTP_409_CONFLICT, "System roles cannot be deleted (their permissions can still be edited)")

    assigned_users = db.query(User).filter(User.role_id == role_id).count()
    if assigned_users:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{assigned_users} user(s) still have this role - reassign them first")

    if _would_lose_all_manage_roles_access(db, role_id, set()):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Refusing to delete: this would leave no active user with MANAGE_ROLES, locking everyone out of role management.",
        )

    log_action(db, current_user.id, "ROLE_DELETED", "Role", role.id, name=role.name)
    db.delete(role)
    db.commit()
