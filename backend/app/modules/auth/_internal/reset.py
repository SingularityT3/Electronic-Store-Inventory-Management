"""Password reset by emailed, single-use, time-limited link (SEC-AUTH-7, FR5.2-IT-3).

The existing password is never revealed: a reset only replaces the hash.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import Settings
from app.modules.audit import audit_service
from app.modules.auth._internal.models import PasswordResetToken, User
from app.modules.auth._internal.passwords import hash_password
from app.modules.auth._internal.sessions import revoke_user_sessions
from app.modules.auth._internal.tokens import hash_token, new_token
from app.modules.auth._internal.users import find_user


@dataclass(frozen=True)
class ResetEmail:
    to: str
    link: str


def request_reset(
    db: Session, identifier: str, settings: Settings, now: datetime
) -> ResetEmail | None:
    """Issue a reset token for an active user with an email address.

    Returns the email to send, or None. Callers must answer the same way in both cases,
    so the response does not reveal whether the account exists.
    """
    user = find_user(db, identifier)
    if user is None or not user.is_active or not user.email:
        return None
    token = new_token()
    db.add(
        PasswordResetToken(
            token_hash=hash_token(token),
            user_id=user.id,
            created_at=now,
            expires_at=now + timedelta(minutes=settings.password_reset_minutes),
        )
    )
    _audit(db, "password_reset_requested", user, "Reset link emailed")
    link = f"{settings.app_base_url.rstrip('/')}/reset-password?token={token}"
    return ResetEmail(to=user.email, link=link)


def create_invite(db: Session, user: User, settings: Settings, now: datetime) -> ResetEmail:
    """Issue the same single-use reset link used for password setup invitations."""
    token = new_token()
    db.add(
        PasswordResetToken(
            token_hash=hash_token(token),
            user_id=user.id,
            created_at=now,
            expires_at=now + timedelta(minutes=settings.password_reset_minutes),
        )
    )
    link = f"{settings.app_base_url.rstrip('/')}/reset-password?token={token}"
    return ResetEmail(to=user.email or "", link=link)


def confirm_reset(db: Session, token: str, new_password: str, now: datetime) -> bool:
    """Set a new password if `token` is unused and unexpired.

    All of the user's reset tokens are then spent and their sessions ended.
    """
    reset = db.scalars(
        select(PasswordResetToken)
        .where(PasswordResetToken.token_hash == hash_token(token))
        .with_for_update()
    ).first()
    if reset is None or reset.used_at is not None or reset.expires_at <= now:
        return False
    user = db.get(User, reset.user_id)
    if user is None or not user.is_active:
        return False
    user.password_hash = hash_password(new_password)
    db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=now)
    )
    revoke_user_sessions(db, user.id)
    _audit(db, "password_reset", user, "Password changed with a reset link")
    return True


def _audit(db: Session, action: str, user: User, details: str) -> None:
    audit_service.record(
        db,
        module="auth",
        action=action,
        user_id=user.id,
        username=user.username,
        entity_type="user",
        entity_id=str(user.id),
        details=details,
    )
