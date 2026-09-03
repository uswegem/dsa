from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models import User, UserRole

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
    user = db.query(User).filter(User.email == email).first()
    if user is None or not user.is_active:
        raise credentials_error
    return user


def require_roles(*roles: UserRole):
    def _checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted for this role")
        return user

    return _checker


require_admin = require_roles(UserRole.ADMIN)
require_business_manager = require_roles(UserRole.BUSINESS_MANAGER, UserRole.ADMIN)
require_branch_manager = require_roles(UserRole.BRANCH_MANAGER, UserRole.ADMIN)
require_any = require_roles(UserRole.ADMIN, UserRole.BUSINESS_MANAGER, UserRole.BRANCH_MANAGER)
