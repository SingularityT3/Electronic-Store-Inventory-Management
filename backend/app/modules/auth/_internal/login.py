"""Credential checks with lockout (UC-01, SEC-AUTH-3..5, SRS A-12).

Every attempt is written to the audit log. Callers commit after `authenticate`
whatever the outcome, so failed attempts and lockouts are kept.
"""

import enum
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache

from sqlalchemy.orm import Session

from app.config import Settings
from app.modules.audit import audit_service
from app.modules.auth._internal.models import User
from app.modules.auth._internal.passwords import hash_password, verify_password
from app.modules.auth._internal.users import find_user


class LoginStatus(enum.Enum):
    OK = "ok"
    INVALID = "invalid"
    LOCKED = "locked"
    DISABLED = "disabled"


@dataclass(frozen=True)
class LoginOutcome:
    status: LoginStatus
    user: User | None = None


@lru_cache
def _dummy_hash() -> str:
    # Verified against for unknown usernames, so they take as long as known ones.
    return hash_password("not-a-real-password")


def _audit(db: Session, action: str, user: User | None, username: str, details: str) -> None:
    audit_service.record(
        db,
        module="auth",
        action=action,
        user_id=user.id if user else None,
        username=user.username if user else username[:150],
        entity_type="user" if user else None,
        entity_id=str(user.id) if user else None,
        details=details,
    )


def authenticate(
    db: Session, identifier: str, password: str, settings: Settings, now: datetime
) -> LoginOutcome:
    """Check a username/email and password.

    Locked and disabled accounts are reported as such only when the password is right;
    otherwise the result is the generic INVALID, so the response never reveals whether a
    username exists. While an account is locked, failures do not extend the lockout.
    """
    user = find_user(db, identifier, for_update=True)
    if user is None:
        verify_password(_dummy_hash(), password)
        _audit(db, "login_failed", None, identifier, "Unknown username")
        return LoginOutcome(LoginStatus.INVALID)

    password_ok = verify_password(user.password_hash, password)

    if user.locked_until is not None and user.locked_until > now:
        _audit(db, "login_denied", user, identifier, "Account locked")
        return LoginOutcome(LoginStatus.LOCKED if password_ok else LoginStatus.INVALID)

    if not password_ok:
        user.failed_login_count += 1
        _audit(db, "login_failed", user, identifier, "Wrong password")
        if user.failed_login_count >= settings.lockout_threshold:
            user.failed_login_count = 0
            user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
            _audit(
                db,
                "account_locked",
                user,
                identifier,
                f"Locked for {settings.lockout_minutes} minutes after "
                f"{settings.lockout_threshold} failed logins",
            )
        return LoginOutcome(LoginStatus.INVALID)

    if not user.is_active:
        _audit(db, "login_denied", user, identifier, "Account disabled")
        return LoginOutcome(LoginStatus.DISABLED)

    user.failed_login_count = 0
    user.locked_until = None
    _audit(db, "login", user, identifier, "Signed in")
    return LoginOutcome(LoginStatus.OK, user)
