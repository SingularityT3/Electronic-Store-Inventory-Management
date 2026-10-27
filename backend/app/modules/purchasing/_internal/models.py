"""Tables owned by the `purchasing` module."""

from datetime import date, datetime
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

Money = Numeric(12, 2)


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    contact_name: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(30))
    address: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (CheckConstraint("btrim(name) <> ''", name="name_not_blank"),)


class SupplierProduct(Base):
    """An item in a supplier's catalog, with the supplier's current price (FR-3.1)."""

    __tablename__ = "supplier_products"

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    variant_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_variants.id", ondelete="RESTRICT")
    )
    supplier_sku: Mapped[str | None] = mapped_column(String(64))
    supplier_price: Mapped[Decimal] = mapped_column(Money)

    __table_args__ = (
        UniqueConstraint(
            "supplier_id", "product_id", "variant_id", postgresql_nulls_not_distinct=True
        ),
        CheckConstraint("supplier_price >= 0", name="supplier_price_non_negative"),
        Index("ix_supplier_products_product_id", "product_id"),
    )


class PurchaseOrder(Base):
    """A purchase order; status follows SRS A-7."""

    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    po_number: Mapped[str] = mapped_column(String(30), unique=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="RESTRICT"))
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(20), server_default=text("'draft'"))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    notes: Mapped[str | None] = mapped_column(Text)
    expected_delivery_date: Mapped[date | None] = mapped_column()
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'submitted', 'partially_received', 'received', 'cancelled')",
            name="status",
        ),
        Index("ix_purchase_orders_supplier_id", "supplier_id"),
        Index("ix_purchase_orders_status", "status"),
    )


class PurchaseOrderLine(Base):
    __tablename__ = "purchase_order_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_order_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_orders.id", ondelete="CASCADE")
    )
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    variant_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_variants.id", ondelete="RESTRICT")
    )
    quantity_ordered: Mapped[int]
    quantity_received: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    unit_price: Mapped[Decimal] = mapped_column(Money)

    __table_args__ = (
        UniqueConstraint(
            "purchase_order_id", "product_id", "variant_id", postgresql_nulls_not_distinct=True
        ),
        CheckConstraint("quantity_ordered > 0", name="quantity_ordered_positive"),
        CheckConstraint("unit_price >= 0", name="unit_price_non_negative"),
        # Receiving more than was ordered is rejected (SRS A-7, FR-3.3).
        CheckConstraint(
            "quantity_received >= 0 AND quantity_received <= quantity_ordered",
            name="quantity_received_within_ordered",
        ),
    )


class PurchaseOrderReceipt(Base):
    """One delivery received against a PO (FR-3.3)."""

    __tablename__ = "po_receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_order_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_orders.id", ondelete="RESTRICT")
    )
    received_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("ix_po_receipts_purchase_order_id", "purchase_order_id"),)


class PurchaseOrderReceiptLine(Base):
    """Quantities for one PO line in a delivery. Only accepted units go into stock."""

    __tablename__ = "po_receipt_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("po_receipts.id", ondelete="CASCADE"))
    po_line_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_order_lines.id", ondelete="RESTRICT")
    )
    quantity_accepted: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    quantity_damaged: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    quantity_short: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    unit_price: Mapped[Decimal] = mapped_column(Money)
    discrepancy_note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("receipt_id", "po_line_id"),
        CheckConstraint(
            "quantity_accepted >= 0 AND quantity_damaged >= 0 AND quantity_short >= 0",
            name="quantities_non_negative",
        ),
        CheckConstraint("unit_price >= 0", name="unit_price_non_negative"),
    )


class PurchaseOrderReceiptSerial(Base):
    """Which serialised units arrived on a receipt line (FR-2.5 traceability)."""

    __tablename__ = "po_receipt_serials"

    receipt_line_id: Mapped[int] = mapped_column(
        ForeignKey("po_receipt_lines.id", ondelete="CASCADE"), primary_key=True
    )
    serial_number_id: Mapped[int] = mapped_column(
        ForeignKey("serial_numbers.id", ondelete="RESTRICT"), primary_key=True
    )

    # A unit is received once.
    __table_args__ = (UniqueConstraint("serial_number_id"),)


class SupplierPriceHistory(Base):
    """Append-only record of prices paid per supplier and item (FR-3.4, SEC-DAT-4).

    A trigger rejects UPDATE and DELETE.
    """

    __tablename__ = "supplier_price_history"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="RESTRICT"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    variant_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_variants.id", ondelete="RESTRICT")
    )
    unit_price: Mapped[Decimal] = mapped_column(Money)
    receipt_line_id: Mapped[int | None] = mapped_column(
        ForeignKey("po_receipt_lines.id", ondelete="RESTRICT")
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("unit_price >= 0", name="unit_price_non_negative"),
        Index(
            "ix_supplier_price_history_supplier_item",
            "supplier_id",
            "product_id",
            "variant_id",
            "recorded_at",
        ),
    )
