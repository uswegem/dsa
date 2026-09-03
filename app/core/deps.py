from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models import Role, User
from app.services.permissions import user_has_any_permission, user_has_permission

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_error
    email = payload.get("sub")
    if email is None:
        raise credentials_error
    user = (
        db.query(User)
        .options(joinedload(User.role).joinedload(Role.permissions))
        .filter(User.email == email)
        .first()
    )
    if user is None or not user.is_active:
        raise credentials_error
    return user


def require_permission(permission_key: str):
    """FastAPI dependency: 403s unless the current user's role grants this
    permission. This is the single reusable enforcement point - endpoints
    should never compare role names/strings directly."""

    def _checker(user: User = Depends(get_current_user)) -> User:
        if not user_has_permission(user, permission_key):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing permission: {permission_key}")
        return user

    return _checker


def require_any_permission(*permission_keys: str):
    """Like require_permission, but passes if the user holds ANY of the
    given permissions (e.g. VIEW_ALL_UPLOADS or VIEW_OWN_BRANCH_UPLOADS) -
    callers then apply their own branch-scoping based on which one."""

    def _checker(user: User = Depends(get_current_user)) -> User:
        if not user_has_any_permission(user, permission_keys):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"Missing any of permissions: {', '.join(permission_keys)}"
            )
        return user

    return _checker
