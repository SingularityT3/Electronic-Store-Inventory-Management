"""Tables owned by the `notifications` module."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
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


class StockAlert(Base):
    """Current low/out-of-stock state for one item at one location."""

    __tablename__ = "stock_alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(Integer)
    variant_id: Mapped[int | None] = mapped_column(Integer)
    location_id: Mapped[int] = mapped_column(Integer)
    product_name: Mapped[str] = mapped_column(String(200))
    sku: Mapped[str] = mapped_column(String(100))
    variant_sku: Mapped[str | None] = mapped_column(String(100))
    location_name: Mapped[str] = mapped_column(String(100))
    alert_type: Mapped[str | None] = mapped_column(String(30))
    quantity: Mapped[int] = mapped_column(Integer)
    threshold: Mapped[int] = mapped_column(Integer)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "product_id",
            "variant_id",
            "location_id",
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint(
            "alert_type IS NULL OR alert_type IN ('low_stock', 'out_of_stock')",
            name="alert_type",
        ),
        CheckConstraint("quantity >= 0", name="quantity_non_negative"),
        CheckConstraint("threshold >= 0", name="threshold_non_negative"),
        CheckConstraint("alert_type IS NULL OR quantity <= threshold", name="below_threshold"),
        CheckConstraint(
            "alert_type <> 'out_of_stock' OR quantity = 0",
            name="out_of_stock_quantity",
        ),
        Index("ix_stock_alerts_location_active", "location_id", "alert_type"),
    )
