"""Tables owned by the `audit` module."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Identity, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AuditLog(Base):
    """Append-only activity log (FR-5.3, NFR-8). A trigger rejects UPDATE and DELETE.

    `user_id` has no foreign key: `auth` sits above `audit`, and an entry must outlive
    the user it names, so `username` is stored as a snapshot.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    user_id: Mapped[int | None]
    username: Mapped[str | None] = mapped_column(String(150))
    module: Mapped[str] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str | None] = mapped_column(String(100))
    entity_id: Mapped[str | None] = mapped_column(String(100))
    details: Mapped[str | None] = mapped_column(Text)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    __table_args__ = (
        Index("ix_audit_log_occurred_at", "occurred_at"),
        Index("ix_audit_log_user_id", "user_id"),
        Index("ix_audit_log_username_lower", func.lower(username)),
        Index("ix_audit_log_action", "action"),
    )
