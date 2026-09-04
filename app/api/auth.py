import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_session, get_current_user
from app.core.security import create_access_token, verify_password
from app.models import User, UserSession
from app.schemas.auth import Token, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive")

    jti = str(uuid.uuid4())
    db.add(UserSession(user_id=user.id, jti=jti))
    db.commit()

    token = create_access_token(subject=user.email, jti=jti)
    return Token(access_token=token)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return UserOut.from_user(current_user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(session: UserSession = Depends(get_current_session), db: Session = Depends(get_db)):
    """Revokes THIS token's session server-side - the frontend's
    auto-logout-on-inactivity calls this too, not just the manual Sign Out
    button, so an idle session can't keep being replayed against the API
    after the browser has moved on. Only this one session is revoked
    (matches a per-tab/per-device token), not every session the user has."""
    session.revoked_at = dt.datetime.now(dt.timezone.utc)
    session.revoked_reason = session.revoked_reason or "logout"
    db.commit()
