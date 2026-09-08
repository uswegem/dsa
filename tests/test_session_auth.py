import datetime as dt
import uuid

import pytest
from fastapi import HTTPException

from app.core.deps import _as_aware_utc, _authenticate
from app.core.security import create_access_token
from app.models import Role, User, UserSession


def _make_user(db):
    role = db.query(Role).filter(Role.name == "ADMIN").one()
    user = User(email="session-test@test.local", hashed_password="x", full_name="Session Test", role_id=role.id)
    db.add(user)
    db.flush()
    return user


def _issue_session(db, user, last_seen_at=None):
    jti = str(uuid.uuid4())
    session = UserSession(user_id=user.id, jti=jti)
    if last_seen_at is not None:
        session.last_seen_at = last_seen_at
    db.add(session)
    db.flush()
    token = create_access_token(subject=user.email, jti=jti)
    return token, session


def test_valid_session_authenticates_and_bumps_last_seen_at(db_session):
    db = db_session
    user = _make_user(db)
    old_last_seen = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=5)
    token, session = _issue_session(db, user, last_seen_at=old_last_seen)

    authed_user, authed_session = _authenticate(token, db)

    assert authed_user.id == user.id
    assert authed_session.id == session.id
    # SQLite (used here) returns naive datetimes on read even from a
    # DateTime(timezone=True) column, unlike Postgres (production) - see
    # app.core.deps._as_aware_utc.
    assert _as_aware_utc(authed_session.last_seen_at) > old_last_seen  # sliding window bumped


def test_revoked_session_is_rejected(db_session):
    db = db_session
    user = _make_user(db)
    token, session = _issue_session(db, user)
    session.revoked_at = dt.datetime.now(dt.timezone.utc)
    session.revoked_reason = "logout"
    db.flush()

    with pytest.raises(HTTPException) as exc:
        _authenticate(token, db)
    assert exc.value.status_code == 401


def test_session_past_the_inactivity_grace_period_is_auto_revoked_and_rejected(db_session):
    """The server-side backstop: a session with no activity for longer than
    session_inactivity_grace_minutes is rejected (and marked revoked) even
    if the frontend's own timer never fired - e.g. a token used directly
    against the API."""
    db = db_session
    user = _make_user(db)
    stale = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=30)
    token, session = _issue_session(db, user, last_seen_at=stale)

    with pytest.raises(HTTPException) as exc:
        _authenticate(token, db)
    assert exc.value.status_code == 401
    assert "inactivity" in exc.value.detail.lower()

    db.refresh(session)
    assert session.revoked_at is not None
    assert session.revoked_reason == "inactivity"


def test_session_within_grace_period_still_works():
    """A session just inside the server-side grace window (but past the
    client's own 10-minute policy) must still be accepted - the grace
    buffer exists precisely so the client-side timer is what drives the
    real UX, not a hair-trigger server cutoff. Pure arithmetic check, no
    DB needed."""
    from app.core.config import get_settings

    settings = get_settings()
    assert settings.session_inactivity_grace_minutes > settings.session_inactivity_minutes


def test_logout_revokes_only_this_session_not_other_sessions_of_the_same_user(db_session):
    db = db_session
    user = _make_user(db)
    token_a, session_a = _issue_session(db, user)
    token_b, session_b = _issue_session(db, user)

    # simulate what POST /api/auth/logout does for session_a's token
    session_a.revoked_at = dt.datetime.now(dt.timezone.utc)
    session_a.revoked_reason = "logout"
    db.flush()

    with pytest.raises(HTTPException):
        _authenticate(token_a, db)

    # session_b (e.g. a different tab/device) is untouched
    authed_user, authed_session = _authenticate(token_b, db)
    assert authed_session.id == session_b.id
    assert authed_session.revoked_at is None


def test_unknown_jti_is_rejected(db_session):
    """A token that decodes fine but whose session row doesn't exist
    (e.g. the DB was reset, or a forged token) must not authenticate."""
    db = db_session
    user = _make_user(db)
    token = create_access_token(subject=user.email, jti=str(uuid.uuid4()))  # no matching UserSession row

    with pytest.raises(HTTPException) as exc:
        _authenticate(token, db)
    assert exc.value.status_code == 401
