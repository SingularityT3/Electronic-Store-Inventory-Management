"""Server-side sessions (NFR-6, SEC-SES-1..3, SRS A-12).

The browser holds a random token in an HttpOnly cookie. Every request looks it up and
checks the idle timeout, the absolute lifetime and the account status; a session that
fails any check is deleted.
"""

from datetime import datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import Settings
from app.modules.auth._internal.models import User, UserSession
from app.modules.auth._internal.tokens import hash_token, new_token

SESSION_COOKIE = "esims_session"

# last_seen_at is refreshed at most this often, to avoid a write on every request.
_TOUCH_INTERVAL = timedelta(seconds=60)


def create_session(db: Session, user: User, settings: Settings, now: datetime) -> str:
    """Start a session for `user` and return the token for the cookie."""
    token = new_token()
    db.add(
        UserSession(
            token_hash=hash_token(token),
            user_id=user.id,
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(hours=settings.session_max_hours),
        )
    )
    return token


def resolve_session(db: Session, token: str, settings: Settings, now: datetime) -> User | None:
    """Return the user of a valid session, or None (deleting the session if it is stale)."""
    session = db.get(UserSession, hash_token(token))
    if session is None:
        return None
    user = db.get(User, session.user_id)
    idle_limit = timedelta(minutes=settings.session_idle_minutes)
    if (
        user is None
        or now >= session.expires_at
        or now - session.last_seen_at >= idle_limit
        or not user.is_active
        or (user.locked_until is not None and user.locked_until > now)
    ):
        db.delete(session)
        return None
    if now - session.last_seen_at >= _TOUCH_INTERVAL:
        session.last_seen_at = now
    return user


def revoke_session(db: Session, token: str) -> int | None:
    """Delete the session for `token`. Returns its user id, or None if there was none."""
    session = db.get(UserSession, hash_token(token))
    if session is None:
        return None
    db.delete(session)
    return session.user_id


def revoke_user_sessions(db: Session, user_id: int) -> None:
    db.execute(delete(UserSession).where(UserSession.user_id == user_id))
