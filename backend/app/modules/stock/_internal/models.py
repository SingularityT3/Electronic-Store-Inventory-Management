"""Tables owned by the `stock` module.

A stocked item is a product (`product_id`) or one of its variants (`product_id` plus
`variant_id`). Products with variants are stocked per variant.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Location(Base):
    """A store or warehouse (FR-2.1). Adding one is a row, not a redesign (NFR-3)."""

    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    type: Mapped[str] = mapped_column(String(20))
    address: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (CheckConstraint("type IN ('store', 'warehouse')", name="type"),)


class StockLevel(Base):
    """On-hand quantity of one item at one location, with its reorder settings.

    `reorder_to_level` NULL means the default of 2 x `reorder_threshold` (SRS A-4).
    """

    __tablename__ = "stock_levels"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    variant_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_variants.id", ondelete="RESTRICT")
    )
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id", ondelete="RESTRICT"))
    quantity: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    reorder_threshold: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    reorder_to_level: Mapped[int | None]
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "product_id", "variant_id", "location_id", postgresql_nulls_not_distinct=True
        ),
        CheckConstraint("quantity >= 0", name="quantity_non_negative"),
        CheckConstraint("reorder_threshold >= 0", name="reorder_threshold_non_negative"),
        CheckConstraint(
            "reorder_to_level IS NULL OR reorder_to_level >= reorder_threshold",
            name="reorder_to_level_at_least_threshold",
        ),
        Index("ix_stock_levels_location_id", "location_id"),
    )


class ItemCost(Base):
    """Weighted average unit cost per item, updated on each PO receipt (SRS A-3).

    `average_cost` NULL means "cost not set".
    """

    __tablename__ = "item_costs"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    variant_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_variants.id", ondelete="RESTRICT")
    )
    average_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("product_id", "variant_id", postgresql_nulls_not_distinct=True),
        CheckConstraint(
            "average_cost IS NULL OR average_cost >= 0", name="average_cost_non_negative"
        ),
    )


class Batch(Base):
    """A received lot of an item (FR-2.5)."""

    __tablename__ = "batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    variant_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_variants.id", ondelete="RESTRICT")
    )
    batch_number: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "product_id", "variant_id", "batch_number", postgresql_nulls_not_distinct=True
        ),
    )


class BatchStock(Base):
    """Aggregate on-hand quantity for one batch at one location (not a per-unit table)."""

    __tablename__ = "batch_stock"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id", ondelete="RESTRICT"))
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id", ondelete="RESTRICT"))
    quantity_received: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    quantity_on_hand: Mapped[int] = mapped_column(Integer, server_default=text("0"))

    __table_args__ = (
        UniqueConstraint("batch_id", "location_id"),
        CheckConstraint("quantity_received >= 0", name="quantity_received_non_negative"),
        CheckConstraint("quantity_on_hand >= 0", name="quantity_on_hand_non_negative"),
        Index("ix_batch_stock_location_id", "location_id"),
    )


class BatchReceipt(Base):
    """Receipt event linking a batch and location to its owning-module reference."""

    __tablename__ = "batch_receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id", ondelete="RESTRICT"))
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id", ondelete="RESTRICT"))
    reference_type: Mapped[str] = mapped_column(String(50))
    reference_id: Mapped[int]
    quantity: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "batch_id",
            "location_id",
            "reference_type",
            "reference_id",
        ),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        Index("ix_batch_receipts_batch_id", "batch_id"),
    )


class SerialNumber(Base):
    """One serialised unit (FR-2.5). Receipt and sale links live in purchasing and sales."""

    __tablename__ = "serial_numbers"

    id: Mapped[int] = mapped_column(primary_key=True)
    serial_number: Mapped[str] = mapped_column(String(100), unique=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    variant_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_variants.id", ondelete="RESTRICT")
    )
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("batches.id", ondelete="RESTRICT"))
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(20), server_default=text("'in_stock'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('in_stock', 'sold', 'returned', 'damaged', 'removed')", name="status"
        ),
        CheckConstraint("btrim(serial_number) <> ''", name="serial_number_not_blank"),
        Index("ix_serial_numbers_product_id", "product_id"),
    )


class StockMovement(Base):
    """Every change to a stock level, with its cause (FR-2.2, FR-2.4, NFR-8).

    `reference_type`/`reference_id` point at the causing record (a sale, receipt or
    transfer), which may belong to a higher module, so there is no foreign key.
    """

    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    variant_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_variants.id", ondelete="RESTRICT")
    )
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id", ondelete="RESTRICT"))
    quantity_change: Mapped[int]
    movement_type: Mapped[str] = mapped_column(String(20))
    reason_code: Mapped[str | None] = mapped_column(String(20))
    reason: Mapped[str | None] = mapped_column(Text)
    reference_type: Mapped[str | None] = mapped_column(String(50))
    reference_id: Mapped[int | None]
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("quantity_change <> 0", name="quantity_change_non_zero"),
        CheckConstraint(
            "movement_type IN ('initial', 'receipt', 'sale', 'return', "
            "'transfer_in', 'transfer_out', 'adjustment')",
            name="movement_type",
        ),
        CheckConstraint(
            "reason_code IS NULL OR reason_code IN ('damage', 'loss', 'correction')",
            name="reason_code",
        ),
        # A manual adjustment must carry a reason (FR-2.4).
        CheckConstraint(
            "movement_type <> 'adjustment' "
            "OR (reason_code IS NOT NULL AND reason IS NOT NULL AND btrim(reason) <> '')",
            name="adjustment_requires_reason",
        ),
        Index("ix_stock_movements_item_location", "product_id", "variant_id", "location_id"),
        Index("ix_stock_movements_created_at", "created_at"),
    )


class StockTransfer(Base):
    """A move of stock between two locations (SRS A-10)."""

    __tablename__ = "stock_transfers"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    variant_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_variants.id", ondelete="RESTRICT")
    )
    from_location_id: Mapped[int] = mapped_column(ForeignKey("locations.id", ondelete="RESTRICT"))
    to_location_id: Mapped[int] = mapped_column(ForeignKey("locations.id", ondelete="RESTRICT"))
    quantity: Mapped[int]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("from_location_id <> to_location_id", name="distinct_locations"),
    )
