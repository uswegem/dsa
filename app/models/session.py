"""
Server-side session tracking - what makes "log out" (manual or the
frontend's auto-logout-on-inactivity) actually revoke access, instead of
just discarding the token client-side while the backend would still
accept it until its (long) absolute expiry.

One row per issued JWT (keyed by its jti claim). app/core/deps.py checks
this on every authenticated request:
  - revoked_at set -> reject (logged out, or auto-revoked for inactivity)
  - now - last_seen_at beyond the server-side inactivity ceiling -> revoke
    + reject (a backstop for tokens used directly against the API, not
    through the frontend's own 10-minute timer - see Settings docstring)
  - otherwise -> last_seen_at is bumped to now (sliding window) and the
    request proceeds
"""
import datetime as dt

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    jti: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String(30))  # "logout" | "inactivity"
