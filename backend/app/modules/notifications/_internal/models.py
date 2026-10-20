"""Tables owned by the `notifications` module."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Notification(Base):
    """An in-app notification for one recipient (FR-8.1, FR-8.2).

    One row per recipient, fanned out per SRS A-6. `location_id` and `reference_id`
    point at higher modules (stock, purchasing), so they have no foreign keys.
    """

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipient_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    location_id: Mapped[int | None]
    reference_type: Mapped[str | None] = mapped_column(String(50))
    reference_id: Mapped[int | None]
    is_read: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("type IN ('low_stock', 'out_of_stock', 'po_status')", name="type"),
        Index("ix_notifications_recipient_unread", "recipient_user_id", "is_read", "created_at"),
    )
