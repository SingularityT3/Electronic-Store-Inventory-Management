"""Tables owned by the `sales` module."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    Sequence,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

Money = Numeric(12, 2)

# Invoice numbers come from a database sequence, so they are unique and increasing even
# under concurrent sales. A rolled-back transaction can leave a gap.
invoice_number_seq = Sequence("invoice_number_seq", metadata=Base.metadata)


class Sale(Base):
    """A completed sale (FR-4.1). Recorded with its stock deduction atomically (NFR-15)."""

    __tablename__ = "sales"

    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id", ondelete="RESTRICT"))
    cashier_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(20), server_default=text("'completed'"))
    subtotal: Mapped[Decimal] = mapped_column(Money)
    tax_total: Mapped[Decimal] = mapped_column(Money, server_default=text("0"))
    total: Mapped[Decimal] = mapped_column(Money)
    discount_total: Mapped[Decimal] = mapped_column(Money, server_default=text("0"))
    customer_name: Mapped[str | None] = mapped_column(String(200))
    idempotency_key: Mapped[str | None] = mapped_column(String(100), unique=True)
    sold_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("status IN ('completed')", name="status"),
        CheckConstraint(
            "subtotal >= 0 AND discount_total >= 0 AND tax_total >= 0 AND total >= 0",
            name="amounts_non_negative",
        ),
        Index("ix_sales_location_sold_at", "location_id", "sold_at"),
        Index("ix_sales_sold_at", "sold_at"),
    )


class SaleLine(Base):
    __tablename__ = "sale_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id", ondelete="RESTRICT"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    variant_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_variants.id", ondelete="RESTRICT")
    )
    quantity: Mapped[int]
    unit_price: Mapped[Decimal] = mapped_column(Money)
    discount_amount: Mapped[Decimal] = mapped_column(Money, server_default=text("0"))
    tax_amount: Mapped[Decimal] = mapped_column(Money, server_default=text("0"))
    line_total: Mapped[Decimal] = mapped_column(Money)

    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint(
            "unit_price >= 0 AND discount_amount >= 0 AND tax_amount >= 0 AND line_total >= 0",
            name="amounts_non_negative",
        ),
        Index("ix_sale_lines_sale_id", "sale_id"),
        Index("ix_sale_lines_product_id", "product_id"),
    )


class SaleLineSerial(Base):
    """Which serialised units were sold on a sale line (FR-2.5 traceability)."""

    __tablename__ = "sale_line_serials"

    sale_line_id: Mapped[int] = mapped_column(
        ForeignKey("sale_lines.id", ondelete="RESTRICT"), primary_key=True
    )
    serial_number_id: Mapped[int] = mapped_column(
        ForeignKey("serial_numbers.id", ondelete="RESTRICT"), primary_key=True
    )


class SaleLineBatch(Base):
    """Quantity allocated from a batch to a sale line for recall and return traceability."""

    __tablename__ = "sale_line_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_line_id: Mapped[int] = mapped_column(
        ForeignKey("sale_lines.id", ondelete="RESTRICT"), index=True
    )
    batch_stock_id: Mapped[int] = mapped_column(ForeignKey("batch_stock.id", ondelete="RESTRICT"))
    quantity: Mapped[int]

    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)


class Payment(Base):
    """How a sale was paid. Card numbers are never stored."""

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id", ondelete="RESTRICT"))
    method: Mapped[str] = mapped_column(String(20))
    amount: Mapped[Decimal] = mapped_column(Money)
    reference: Mapped[str | None] = mapped_column(String(100))
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("method IN ('cash', 'card', 'upi', 'other')", name="method"),
        CheckConstraint("amount > 0", name="amount_positive"),
        Index("ix_payments_sale_id", "sale_id"),
    )


class Return(Base):
    """A customer return against a sale (FR-4.2).

    `approved_by` is the Manager who approved a return past the 30-day window (A-1, A-11).
    """

    __tablename__ = "returns"

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id", ondelete="RESTRICT"))
    processed_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    reason: Mapped[str | None] = mapped_column(Text)
    refund_total: Mapped[Decimal] = mapped_column(Money, server_default=text("0"))
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("refund_total >= 0", name="refund_total_non_negative"),
        Index("ix_returns_sale_id", "sale_id"),
    )


class ReturnLine(Base):
    """A returned quantity of a sale line. Damaged units are recorded, not restocked."""

    __tablename__ = "return_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    return_id: Mapped[int] = mapped_column(ForeignKey("returns.id", ondelete="RESTRICT"))
    sale_line_id: Mapped[int] = mapped_column(ForeignKey("sale_lines.id", ondelete="RESTRICT"))
    quantity: Mapped[int]
    condition: Mapped[str] = mapped_column(String(20))
    restocked: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    refund_amount: Mapped[Decimal] = mapped_column(Money, server_default=text("0"))

    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("condition IN ('resaleable', 'damaged')", name="condition"),
        CheckConstraint("condition = 'resaleable' OR NOT restocked", name="damaged_not_restocked"),
        CheckConstraint("refund_amount >= 0", name="refund_amount_non_negative"),
    )


class ReturnLineSerial(Base):
    """A serial restored by a return; the original sale-line link remains immutable."""

    __tablename__ = "return_line_serials"

    return_line_id: Mapped[int] = mapped_column(
        ForeignKey("return_lines.id", ondelete="RESTRICT"), primary_key=True
    )
    serial_number_id: Mapped[int] = mapped_column(
        ForeignKey("serial_numbers.id", ondelete="RESTRICT"), primary_key=True
    )


class ReturnLineBatch(Base):
    """Quantity returned from a specific original sale allocation."""

    __tablename__ = "return_line_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    return_line_id: Mapped[int] = mapped_column(
        ForeignKey("return_lines.id", ondelete="RESTRICT"), index=True
    )
    sale_line_batch_id: Mapped[int] = mapped_column(
        ForeignKey("sale_line_batches.id", ondelete="RESTRICT")
    )
    quantity: Mapped[int]

    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)


class Invoice(Base):
    """The invoice for a sale (FR-4.3): one per sale, with a unique sequential number."""

    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id", ondelete="RESTRICT"), unique=True)
    invoice_number: Mapped[int] = mapped_column(
        BigInteger, invoice_number_seq, server_default=invoice_number_seq.next_value()
    )
    total: Mapped[Decimal] = mapped_column(Money)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    notes: Mapped[str | None] = mapped_column(Text)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))

    __table_args__ = (
        UniqueConstraint("invoice_number"),
        CheckConstraint("total >= 0", name="total_non_negative"),
    )
