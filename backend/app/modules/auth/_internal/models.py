"""Tables owned by the `auth` module."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

ROLES = {"admin": "Admin", "manager": "Manager", "staff": "Staff", "cashier": "Cashier"}


class Role(Base):
    """The four fixed roles (FR-5.1). Rows are inserted by the initial migration."""

    __tablename__ = "roles"

    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)


class User(Base):
    """A user account.

    `location_id` refers to `stock.locations` but has no foreign key, because `stock`
    sits above `auth`. Staff and Cashier must have one (SRS A-9).
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(150))
    email: Mapped[str | None] = mapped_column(String(254), unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(ForeignKey("roles.code"))
    location_id: Mapped[int | None]
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    failed_login_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("uq_users_username_lower", func.lower(username), unique=True),
        Index("uq_users_email_lower", func.lower(email), unique=True),
        Index("ix_users_role", "role"),
        CheckConstraint(
            "role NOT IN ('staff', 'cashier') OR location_id IS NOT NULL",
            name="location_required_for_role",
        ),
        CheckConstraint("failed_login_count >= 0", name="failed_login_count_non_negative"),
    )


class UserSession(Base):
    """A signed-in browser session (NFR-6, SEC-SES-1..3).

    The cookie carries a random token; only its SHA-256 is stored, so a database leak
    does not expose usable sessions. Logout deletes the row.
    """

    __tablename__ = "user_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_user_sessions_user_id", "user_id"),)


class PasswordResetToken(Base):
    """A single-use, time-limited password reset token (SEC-AUTH-7). Stored hashed."""

    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_password_reset_tokens_user_id", "user_id"),)
