"""User lookups shared by login and password reset."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.auth._internal.models import User


def find_user(db: Session, identifier: str, *, for_update: bool = False) -> User | None:
    """Find a user by username or email, both case-insensitive. Username wins a tie."""
    identifier = identifier.strip().lower()
    if not identifier:
        return None
    for column in (User.username, User.email):
        query = select(User).where(func.lower(column) == identifier)
        if for_update:
            query = query.with_for_update()
        user = db.scalars(query).first()
        if user is not None:
            return user
    return None
