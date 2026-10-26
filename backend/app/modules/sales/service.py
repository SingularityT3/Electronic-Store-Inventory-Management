"""Atomic sale recording service."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.modules.audit import audit_service
from app.modules.product import SaleProduct, sale_product
from app.modules.sales._internal.models import Invoice, Payment, Sale, SaleLine
from app.modules.stock import InsufficientStockError, stock_positions, update_stock

CENT = Decimal("0.01")
MAX_QUANTITY = 100_000
DiscountType = Literal["percentage", "amount"]


class SaleInputError(Exception):
    def __init__(self, errors: list[dict[str, object]]) -> None:
        super().__init__("The sale contains invalid fields.")
        self.errors = errors


class SaleStockError(Exception):
    def __init__(self, errors: list[dict[str, object]]) -> None:
        super().__init__("The requested stock is not available.")
        self.errors = errors


@dataclass(frozen=True)
class SaleLineInput:
    product_id: int
    variant_id: int | None
    quantity: int
    discount: Decimal
    discount_type: DiscountType


@dataclass(frozen=True)
class PaymentInput:
    method: str
    amount: Decimal
    reference: str | None


@dataclass(frozen=True)
class PreparedLine:
    product: SaleProduct
    quantity: int
    discount_amount: Decimal
    unit_price: Decimal
    taxable_amount: Decimal
    tax_amount: Decimal
    line_total: Decimal


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _line_error(index: int, field: str, message: str) -> dict[str, object]:
    return {"line": index, "field": field, "message": message}


def _prepare_lines(
    db: Session, lines: list[SaleLineInput], settings: Settings
) -> tuple[list[PreparedLine], Decimal, Decimal, Decimal, Decimal]:
    errors: list[dict[str, object]] = []
    if not lines:
        raise SaleInputError([{"field": "lines", "message": "At least one line is required."}])

    merged: dict[tuple[int, int | None], tuple[int, Decimal]] = {}
    products: dict[tuple[int, int | None], SaleProduct] = {}
    for index, line in enumerate(lines):
        if line.quantity < 1 or line.quantity > MAX_QUANTITY:
            errors.append(_line_error(index, "quantity", "Quantity must be between 1 and 100000."))
            continue
        if line.discount < 0:
            errors.append(_line_error(index, "discount", "Discount cannot be negative."))
            continue
        product = sale_product(db, line.product_id, line.variant_id)
        if product is None or not product.product_active:
            errors.append(_line_error(index, "product_id", "Product or variant not found."))
            continue
        if line.variant_id is not None and not product.variant_active:
            errors.append(_line_error(index, "variant_id", "Product or variant not found."))
            continue
        if line.variant_id is None and product.has_active_variants:
            errors.append(
                _line_error(index, "variant_id", "A product with variants must be sold by variant.")
            )
            continue
        gross = _money(product.unit_price * line.quantity)
        discount = (
            _money(gross * line.discount / Decimal("100"))
            if line.discount_type == "percentage"
            else _money(line.discount)
        )
        if discount > gross:
            errors.append(_line_error(index, "discount", "Discount cannot exceed the line amount."))
            continue
        key = (line.product_id, line.variant_id)
        previous_quantity, previous_discount = merged.get(key, (0, Decimal("0")))
        merged[key] = (previous_quantity + line.quantity, previous_discount + discount)
        products[key] = product

    if errors:
        raise SaleInputError(errors)

    prepared: list[PreparedLine] = []
    for key in sorted(merged, key=lambda item: (item[0], item[1] or 0)):
        quantity, discount = merged[key]
        product = products[key]
        gross = _money(product.unit_price * quantity)
        discount = _money(discount)
        taxable = _money(gross - discount)
        tax = _money(taxable * settings.gst_rate / Decimal("100"))
        prepared.append(
            PreparedLine(
                product,
                quantity,
                discount,
                _money(product.unit_price),
                taxable,
                tax,
                _money(taxable + tax),
            )
        )
    subtotal = _money(sum((line.unit_price * line.quantity for line in prepared), Decimal("0")))
    discount_total = _money(sum((line.discount_amount for line in prepared), Decimal("0")))
    tax_total = _money(sum((line.tax_amount for line in prepared), Decimal("0")))
    total = _money(sum((line.line_total for line in prepared), Decimal("0")))
    return prepared, subtotal, discount_total, tax_total, total


def _validate_payments(payments: list[PaymentInput], total: Decimal) -> None:
    errors: list[dict[str, object]] = []
    if not payments:
        errors.append({"field": "payments", "message": "At least one payment is required."})
    for index, payment in enumerate(payments):
        if payment.method not in {"cash", "card", "upi", "other"}:
            errors.append(
                {"payment": index, "field": "method", "message": "Unknown payment method."}
            )
        if payment.amount <= 0:
            errors.append(
                {"payment": index, "field": "amount", "message": "Payment amount must be positive."}
            )
        if payment.reference and len(payment.reference) > 100:
            errors.append(
                {"payment": index, "field": "reference", "message": "Reference is too long."}
            )
    if not errors and _money(sum((payment.amount for payment in payments), Decimal("0"))) != total:
        errors.append(
            {"field": "payments", "message": "Payment amounts must equal the sale total."}
        )
    if errors:
        raise SaleInputError(errors)


def record_sale(
    db: Session,
    *,
    location_id: int,
    cashier_id: int,
    cashier_username: str,
    lines: list[SaleLineInput],
    payments: list[PaymentInput],
    customer_name: str | None,
    idempotency_key: str | None,
    settings: Settings,
) -> Sale:
    if idempotency_key:
        existing = db.scalar(select(Sale).where(Sale.idempotency_key == idempotency_key))
        if existing is not None:
            if existing.cashier_id != cashier_id or existing.location_id != location_id:
                raise SaleInputError(
                    [{"field": "idempotency_key", "message": "Idempotency key is already in use."}]
                )
            return existing

    prepared, subtotal, discount_total, tax_total, total = _prepare_lines(db, lines, settings)
    _validate_payments(payments, total)
    sale = Sale(
        location_id=location_id,
        cashier_id=cashier_id,
        subtotal=subtotal,
        discount_total=discount_total,
        tax_total=tax_total,
        total=total,
        customer_name=customer_name.strip() if customer_name else None,
        idempotency_key=idempotency_key,
    )
    db.add(sale)
    db.flush()

    available = {
        (position.product_id, position.variant_id): position.quantity
        for position in stock_positions(
            db, location_id=location_id, product_ids=[line.product.product_id for line in prepared]
        )
    }
    stock_errors: list[dict[str, object]] = []
    for line in prepared:
        key = (line.product.product_id, line.product.variant_id)
        current = available.get(key, 0)
        if current < line.quantity:
            stock_errors.append(
                {
                    "line": f"{line.product.product_id}:{line.product.variant_id or ''}",
                    "message": "Out of stock" if current == 0 else "Insufficient stock",
                    "available": current,
                }
            )
        try:
            update_stock(
                db,
                product_id=line.product.product_id,
                variant_id=line.product.variant_id,
                location_id=location_id,
                quantity_delta=-line.quantity,
                movement_type="sale",
                user_id=cashier_id,
                username=cashier_username,
                reference_type="sale",
                reference_id=sale.id,
                record_audit=False,
            )
        except InsufficientStockError:
            if not any(item["line"] == f"{key[0]}:{key[1] or ''}" for item in stock_errors):
                stock_errors.append(
                    {
                        "line": f"{key[0]}:{key[1] or ''}",
                        "message": "Insufficient stock" if current else "Out of stock",
                        "available": current,
                    }
                )
    if stock_errors:
        raise SaleStockError(stock_errors)

    db.add_all(
        [
            SaleLine(
                sale_id=sale.id,
                product_id=line.product.product_id,
                variant_id=line.product.variant_id,
                quantity=line.quantity,
                unit_price=line.unit_price,
                discount_amount=line.discount_amount,
                tax_amount=line.tax_amount,
                line_total=line.line_total,
            )
            for line in prepared
        ]
    )
    db.add_all(
        [
            Payment(
                sale_id=sale.id,
                method=payment.method,
                amount=_money(payment.amount),
                reference=payment.reference.strip() if payment.reference else None,
            )
            for payment in payments
        ]
    )
    db.add(Invoice(sale_id=sale.id, total=total))
    audit_service.record(
        db,
        module="sales",
        action="sale_recorded",
        user_id=cashier_id,
        username=cashier_username,
        entity_type="sale",
        entity_id=str(sale.id),
        details=(
            f"Recorded sale at location {location_id} with "
            f"{sum(line.quantity for line in prepared)} items, total {total}, "
            f"payment methods {', '.join(payment.method for payment in payments)}."
        ),
        after={
            "location_id": location_id,
            "item_count": sum(line.quantity for line in prepared),
            "total": total,
        },
    )
    db.flush()
    return sale


class SalesService(Protocol):
    def record(self, db: Session, **kwargs: object) -> Sale: ...
