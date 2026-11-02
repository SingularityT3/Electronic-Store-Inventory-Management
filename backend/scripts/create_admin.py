"""Create an Admin account, e.g. the first one on a new installation.

    python -m scripts.create_admin <username> "<Full name>" [--email admin@example.com]

The password is read from ADMIN_PASSWORD if it is set, otherwise asked for twice at the prompt;
it is never echoed, logged or stored in plain text (SEC-AUTH-2). The account is recorded in the
audit log as created by `system`. Everyone else is then added by this Admin on the User
management screen.
"""

import argparse
import getpass
import os
import sys

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.modules.audit import audit_service
from app.modules.auth._internal.models import User
from app.modules.auth._internal.passwords import hash_password
from migrations import models  # noqa: F401  (registers every table, so all FKs resolve)

MIN_PASSWORD_LENGTH = 8


class CreateAdminError(Exception):
    pass


def create_admin(
    engine: Engine, *, username: str, full_name: str, password: str, email: str | None = None
) -> int:
    """Add an active Admin and return its id. Refuses a taken username or email, or a short
    password."""
    username, full_name = username.strip(), full_name.strip()
    email = email.strip().lower() if email else None
    if not username or not full_name:
        raise CreateAdminError("Username and full name are required.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise CreateAdminError(f"The password must be at least {MIN_PASSWORD_LENGTH} characters.")
    with Session(engine) as session:
        if session.scalar(select(User.id).where(func.lower(User.username) == username.lower())):
            raise CreateAdminError(f"A user named {username!r} already exists.")
        if email and session.scalar(select(User.id).where(func.lower(User.email) == email)):
            raise CreateAdminError(f"A user with the email {email!r} already exists.")
        user = User(
            username=username,
            full_name=full_name,
            email=email,
            password_hash=hash_password(password),
            role="admin",
        )
        session.add(user)
        session.flush()
        audit_service.record(
            session,
            module="auth",
            action="user_created",
            username="system",
            entity_type="user",
            entity_id=str(user.id),
            details=f"Admin account {username} created from the command line.",
            after={"username": username, "role": "admin", "is_active": True},
        )
        session.commit()
        return user.id


def _password() -> str:
    if os.environ.get("ADMIN_PASSWORD"):
        return os.environ["ADMIN_PASSWORD"]
    first = getpass.getpass("Password for the new Admin: ")
    if first != getpass.getpass("Repeat the password: "):
        sys.exit("The passwords do not match.")
    return first


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("username")
    parser.add_argument("full_name")
    parser.add_argument("--email", default=None)
    args = parser.parse_args()
    try:
        user_id = create_admin(
            get_engine(),
            username=args.username,
            full_name=args.full_name,
            email=args.email,
            password=_password(),
        )
    except CreateAdminError as exc:
        sys.exit(str(exc))
    print(f"Admin {args.username} created (id {user_id}). Sign in and add the other users.")


if __name__ == "__main__":
    main()
