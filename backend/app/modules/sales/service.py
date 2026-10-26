"""Atomic sale recording service."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal, Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.modules.audit import audit_service
from app.modules.product import SaleProduct, sale_product
from app.modules.sales._internal.models import (
    Invoice,
    Payment,
    ReturnLine,
    ReturnLineBatch,
    ReturnLineSerial,
    Sale,
    SaleLine,
    SaleLineBatch,
    SaleLineSerial,
)
from app.modules.stock import (
    InsufficientStockError,
    consume_tracked_stock,
    restore_batch_stock,
    restore_serial_stock,
    stock_positions,
)

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


class SaleTrackingError(Exception):
    """A tracked item could not be sold or restored consistently."""


@dataclass(frozen=True)
class SaleLineInput:
    product_id: int
    variant_id: int | None
    quantity: int
    discount: Decimal
    discount_type: DiscountType
    serial_numbers: tuple[str, ...] = ()


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
    serial_numbers: tuple[str, ...] = ()


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

    merged: dict[tuple[int, int | None], tuple[int, Decimal, list[str]]] = {}
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
        if product.tracking_mode == "serial" and len(line.serial_numbers) != line.quantity:
            errors.append(
                _line_error(index, "serial_numbers", "Provide one serial number for each unit.")
            )
            continue
        if product.tracking_mode != "serial" and line.serial_numbers:
            errors.append(
                _line_error(
                    index, "serial_numbers", "Serial numbers are only valid for serial items."
                )
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
        previous_quantity, previous_discount, previous_serials = merged.get(
            key, (0, Decimal("0"), [])
        )
        merged[key] = (
            previous_quantity + line.quantity,
            previous_discount + discount,
            previous_serials + list(line.serial_numbers),
        )
        products[key] = product

    if errors:
        raise SaleInputError(errors)

    prepared: list[PreparedLine] = []
    for key in sorted(merged, key=lambda item: (item[0], item[1] or 0)):
        quantity, discount, serial_numbers = merged[key]
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
                tuple(serial_numbers),
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
    tracking_results = {}
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
            tracking_results[key] = consume_tracked_stock(
                db,
                product_id=line.product.product_id,
                variant_id=line.product.variant_id,
                location_id=location_id,
                quantity=line.quantity,
                serial_numbers=line.serial_numbers,
                user_id=cashier_id,
                username=cashier_username,
                sale_id=sale.id,
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
        except ValueError as exc:
            raise SaleInputError(
                [
                    {
                        "line": f"{key[0]}:{key[1] or ''}",
                        "field": (
                            "serial_numbers"
                            if line.product.tracking_mode == "serial"
                            else "product_id"
                        ),
                        "message": str(exc),
                    }
                ]
            ) from exc
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
    db.flush()
    sale_lines = db.scalars(
        select(SaleLine).where(SaleLine.sale_id == sale.id).order_by(SaleLine.id)
    ).all()
    for sale_line in sale_lines:
        result = tracking_results[(sale_line.product_id, sale_line.variant_id)]
        db.add_all(
            SaleLineSerial(sale_line_id=sale_line.id, serial_number_id=serial_id)
            for serial_id in result.serial_number_ids
        )
        db.add_all(
            SaleLineBatch(
                sale_line_id=sale_line.id,
                batch_stock_id=allocation.batch_stock_id,
                quantity=allocation.quantity,
            )
            for allocation in result.batch_allocations
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


def restore_returned_serials(
    db: Session,
    *,
    return_line_id: int,
    serial_number_ids: tuple[int, ...],
    actor_id: int,
    actor_username: str,
) -> None:
    """Restore returned serials in the caller's return transaction."""
    return_line = db.get(ReturnLine, return_line_id)
    if (
        return_line is None
        or not return_line.restocked
        or return_line.condition != "resaleable"
        or len(serial_number_ids) != return_line.quantity
        or len(serial_number_ids) != len(set(serial_number_ids))
    ):
        raise SaleTrackingError("Returned serial units do not match the restocked return line.")
    linked = set(
        db.scalars(
            select(SaleLineSerial.serial_number_id).where(
                SaleLineSerial.sale_line_id == return_line.sale_line_id,
                SaleLineSerial.serial_number_id.in_(serial_number_ids),
            )
        )
    )
    if linked != set(serial_number_ids):
        raise SaleTrackingError("Serial number was not sold on this invoice line.")
    for serial_id in serial_number_ids:
        latest_sale_line = db.scalar(
            select(SaleLineSerial.sale_line_id)
            .where(SaleLineSerial.serial_number_id == serial_id)
            .order_by(SaleLineSerial.sale_line_id.desc())
            .limit(1)
        )
        if latest_sale_line != return_line.sale_line_id:
            raise SaleTrackingError("Serial number has since been sold on another invoice.")
    sale = db.scalar(
        select(Sale)
        .join(SaleLine, SaleLine.sale_id == Sale.id)
        .where(SaleLine.id == return_line.sale_line_id)
    )
    if sale is None:
        raise RuntimeError("Return line has no original sale.")
    restore_serial_stock(
        db,
        serial_number_ids=serial_number_ids,
        location_id=sale.location_id,
        user_id=actor_id,
        username=actor_username,
        return_line_id=return_line_id,
    )
    db.add_all(
        ReturnLineSerial(return_line_id=return_line_id, serial_number_id=serial_id)
        for serial_id in serial_number_ids
    )
    audit_service.record(
        db,
        module="sales",
        action="tracked_return_restocked",
        user_id=actor_id,
        username=actor_username,
        entity_type="return_line",
        entity_id=str(return_line_id),
        details=f"Restocked {len(serial_number_ids)} serial-tracked unit(s).",
        after={"serial_number_ids": list(serial_number_ids), "original_sale_id": sale.id},
    )
    db.flush()


def restore_returned_batch_units(
    db: Session,
    *,
    return_line_id: int,
    actor_id: int,
    actor_username: str,
) -> None:
    """Restore batch quantities against their original sale allocations transactionally."""
    return_line = db.get(ReturnLine, return_line_id)
    if return_line is None or not return_line.restocked or return_line.condition != "resaleable":
        raise SaleTrackingError("Return line is not eligible for batch restocking.")
    sale = db.scalar(
        select(Sale)
        .join(SaleLine, SaleLine.sale_id == Sale.id)
        .where(SaleLine.id == return_line.sale_line_id)
    )
    if sale is None:
        raise RuntimeError("Return line has no original sale.")
    allocations = db.scalars(
        select(SaleLineBatch)
        .where(SaleLineBatch.sale_line_id == return_line.sale_line_id)
        .order_by(SaleLineBatch.id)
        .with_for_update()
    ).all()
    if (
        db.scalar(
            select(ReturnLineBatch.id)
            .where(ReturnLineBatch.return_line_id == return_line_id)
            .limit(1)
        )
        is not None
    ):
        raise SaleTrackingError("Return line has already been restocked.")
    remaining = return_line.quantity
    for allocation in allocations:
        previously_returned = db.scalar(
            select(func.coalesce(func.sum(ReturnLineBatch.quantity), 0)).where(
                ReturnLineBatch.sale_line_batch_id == allocation.id
            )
        )
        available_to_return = allocation.quantity - int(previously_returned or 0)
        returned = min(remaining, available_to_return)
        if not returned:
            continue
        restore_batch_stock(
            db,
            batch_stock_id=allocation.batch_stock_id,
            location_id=sale.location_id,
            quantity=returned,
            user_id=actor_id,
            username=actor_username,
            return_line_id=return_line_id,
        )
        db.add(
            ReturnLineBatch(
                return_line_id=return_line_id,
                sale_line_batch_id=allocation.id,
                quantity=returned,
            )
        )
        remaining -= returned
        if remaining == 0:
            break
    if remaining:
        raise SaleTrackingError("Returned quantity exceeds the sold batch quantity.")
    audit_service.record(
        db,
        module="sales",
        action="tracked_return_restocked",
        user_id=actor_id,
        username=actor_username,
        entity_type="return_line",
        entity_id=str(return_line_id),
        details=f"Restocked {return_line.quantity} batch-tracked unit(s).",
        after={"sale_line_id": return_line.sale_line_id, "original_sale_id": sale.id},
    )
    db.flush()


class SalesService(Protocol):
    def record(self, db: Session, **kwargs: object) -> Sale: ...
