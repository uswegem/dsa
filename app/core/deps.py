import datetime as dt

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models import Role, User, UserSession
from app.services.permissions import user_has_any_permission, user_has_permission

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
settings = get_settings()

CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)
SESSION_EXPIRED_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Session expired due to inactivity - please sign in again.",
    headers={"WWW-Authenticate": "Bearer"},
)


def _as_aware_utc(value: dt.datetime) -> dt.datetime:
    """SQLite (used in tests) returns naive datetimes even for
    DateTime(timezone=True) columns - it has no native tz-aware type, so
    SQLAlchemy's SQLite dialect can't preserve one on read. PostgreSQL
    (production) does this correctly end-to-end. Normalizing here (rather
    than trusting the driver) keeps the inactivity comparison below correct
    on both, instead of only ever being exercised on Postgres."""
    return value if value.tzinfo is not None else value.replace(tzinfo=dt.timezone.utc)


def _authenticate(token: str, db: Session) -> tuple[User, UserSession]:
    """Shared by get_current_user / get_current_session: decode the token,
    load its UserSession, enforce revocation and the server-side inactivity
    ceiling, then bump last_seen_at (sliding window) - see
    Settings.session_inactivity_minutes/session_inactivity_grace_minutes
    for why there are two numbers, not one."""
    payload = decode_access_token(token)
    if payload is None:
        raise CREDENTIALS_ERROR
    email = payload.get("sub")
    jti = payload.get("jti")
    if email is None or jti is None:
        raise CREDENTIALS_ERROR

    user = (
        db.query(User)
        .options(joinedload(User.role).joinedload(Role.permissions))
        .filter(User.email == email)
        .first()
    )
    if user is None or not user.is_active:
        raise CREDENTIALS_ERROR

    session = db.query(UserSession).filter(UserSession.jti == jti).first()
    if session is None or session.user_id != user.id:
        raise CREDENTIALS_ERROR
    if session.revoked_at is not None:
        raise SESSION_EXPIRED_ERROR if session.revoked_reason == "inactivity" else CREDENTIALS_ERROR

    now = dt.datetime.now(dt.timezone.utc)
    if now - _as_aware_utc(session.last_seen_at) > dt.timedelta(minutes=settings.session_inactivity_grace_minutes):
        session.revoked_at = now
        session.revoked_reason = "inactivity"
        db.commit()
        raise SESSION_EXPIRED_ERROR

    session.last_seen_at = now
    db.commit()
    return user, session


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    user, _session = _authenticate(token, db)
    return user


def get_current_session(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> UserSession:
    """For endpoints that need to act on the caller's OWN session (right
    now, just POST /api/auth/logout) rather than the user identity."""
    _user, session = _authenticate(token, db)
    return session


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
