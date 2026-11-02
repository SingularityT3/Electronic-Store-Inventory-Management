"""Set a user's password from the server, for installations without outgoing email.

    python -m scripts.set_password <username>

Normally new users get an invite link by email and forgotten passwords are reset from the
sign-in page. Without SMTP neither email arrives, so the administrator who runs the server sets
a password here and hands it over in person; the user should change it with "Forgot password?"
once email works. The password is read from NEW_PASSWORD if set, otherwise asked for twice; it
is never shown or logged. Unused reset links are spent, the user's sessions are ended, any
lockout is cleared, and the change is audited.
"""

import argparse
import getpass
import os
import sys
from datetime import UTC, datetime

from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session

from app.db import get_engine
from app.modules.audit import audit_service
from app.modules.auth._internal.models import PasswordResetToken, User
from app.modules.auth._internal.passwords import hash_password
from app.modules.auth._internal.sessions import revoke_user_sessions
from migrations import models  # noqa: F401  (registers every table, so all FKs resolve)
from scripts.create_admin import MIN_PASSWORD_LENGTH


class SetPasswordError(Exception):
    pass


def set_password(engine: Engine, *, username: str, password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise SetPasswordError(f"The password must be at least {MIN_PASSWORD_LENGTH} characters.")
    with Session(engine) as session:
        user = session.scalar(
            select(User).where(func.lower(User.username) == username.strip().lower())
        )
        if user is None:
            raise SetPasswordError(f"No user named {username!r}.")
        if not user.is_active:
            raise SetPasswordError(f"{user.username} is deactivated; reactivate the account first.")
        user.password_hash = hash_password(password)
        user.failed_login_count = 0
        user.locked_until = None
        session.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
            .values(used_at=datetime.now(UTC))
        )
        revoke_user_sessions(session, user.id)
        audit_service.record(
            session,
            module="auth",
            action="password_set_by_operator",
            username="system",
            entity_type="user",
            entity_id=str(user.id),
            details=f"Password for {user.username} set from the command line.",
        )
        session.commit()


def _password() -> str:
    if os.environ.get("NEW_PASSWORD"):
        return os.environ["NEW_PASSWORD"]
    first = getpass.getpass("New password: ")
    if first != getpass.getpass("Repeat the password: "):
        sys.exit("The passwords do not match.")
    return first


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("username")
    args = parser.parse_args()
    try:
        set_password(get_engine(), username=args.username, password=_password())
    except SetPasswordError as exc:
        sys.exit(str(exc))
    print(f"Password for {args.username} set. Their open sessions were signed out.")


if __name__ == "__main__":
    main()
