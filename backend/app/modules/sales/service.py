"""Atomic sale recording and customer return service."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal, Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.modules.audit import audit_service
from app.modules.auth import (
    Permission,
    has_permission,
    username_by_id,
    verify_override,
)
from app.modules.product import (
    SaleProduct,
    product_stock_item,
    sale_product,
)
from app.modules.sales._internal.models import (
    Invoice,
    Payment,
    Return,
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
    location_name,
    restore_batch_stock,
    restore_serial_stock,
    serial_number_labels,
    stock_positions,
    update_stock,
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


class InvoiceNotFoundError(Exception):
    """Raised when an invoice cannot be found or is invalid."""


class ReturnLateApprovalRequiredError(Exception):
    """Raised when a return is past the return window and lacks manager approval."""


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


@dataclass(frozen=True)
class ReturnLineInput:
    sale_line_id: int
    quantity: int
    condition: Literal["resaleable", "damaged"]
    serial_number_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class ReturnCreditNoteLine:
    id: int
    sale_line_id: int
    product_id: int
    product_name: str
    sku: str
    variant_id: int | None
    variant_sku: str | None
    quantity: int
    condition: str
    restocked: bool
    refund_amount: Decimal
    serial_numbers: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReturnCreditNote:
    credit_note_number: str
    return_id: int
    sale_id: int
    invoice_number: int
    created_at: datetime
    sold_at: datetime
    location_id: int
    location_name: str
    reason: str
    processor_username: str
    approver_username: str | None
    refund_total: Decimal
    non_sellable_quantity: int
    lines: list[ReturnCreditNoteLine]


@dataclass(frozen=True)
class SaleLookupLineData:
    id: int
    product_id: int
    product_name: str
    sku: str
    variant_id: int | None
    variant_sku: str | None
    variant_attributes: dict[str, object] | None
    quantity: int
    unit_price: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    line_total: Decimal
    serial_numbers: list[str]
    quantity_returned: int
    quantity_returnable: int
    returnable_serials: list[str]
    returnable_serial_ids: list[int]


@dataclass(frozen=True)
class SaleLookupData:
    sale: Sale
    invoice: Invoice
    location_name: str
    lines: list[SaleLookupLineData]
    payments: list[Payment]
    days_since_sale: int
    return_window_days: int
    requires_manager_approval: bool
    return_status: Literal["none", "partially_returned", "fully_returned"]


def parse_invoice_number(raw: str | int) -> int | None:
    """Parse bare integer or case-insensitive 'INV-...' format into an invoice number."""
    if isinstance(raw, int):
        return raw if raw > 0 else None
    s = str(raw).strip()
    if not s:
        return None
    if s.upper().startswith("INV-"):
        s = s[4:].strip()
    if not s.isdigit():
        return None
    try:
        val = int(s)
        return val if val > 0 else None
    except ValueError:
        return None


def compute_line_refund(
    line_total: Decimal,
    sold_quantity: int,
    already_returned: int,
    now_returned: int,
) -> Decimal:
    """Proportionally allocate line refund using ROUND_HALF_UP so cumulative refunds match."""
    cumulative_before = _money(line_total * Decimal(already_returned) / Decimal(sold_quantity))
    cumulative_after = _money(
        line_total * Decimal(already_returned + now_returned) / Decimal(sold_quantity)
    )
    return cumulative_after - cumulative_before


def compute_sale_return_status(
    line_counts: list[tuple[int, int]],
) -> Literal["none", "partially_returned", "fully_returned"]:
    """Compute sale return status: 'none', 'partially_returned', or 'fully_returned'."""
    if not line_counts:
        return "none"
    total_returned = sum(returned for _, returned in line_counts)
    if total_returned == 0:
        return "none"
    if all(returned >= sold for sold, returned in line_counts):
        return "fully_returned"
    return "partially_returned"


def get_sale_return_status(
    db: Session, sale_id: int
) -> Literal["none", "partially_returned", "fully_returned"]:
    """Get computed return status for a sale."""
    lines = db.scalars(select(SaleLine).where(SaleLine.sale_id == sale_id)).all()
    line_counts: list[tuple[int, int]] = []
    for line in lines:
        returned_qty = db.scalar(
            select(func.coalesce(func.sum(ReturnLine.quantity), 0)).where(
                ReturnLine.sale_line_id == line.id
            )
        )
        line_counts.append((line.quantity, int(returned_qty or 0)))
    return compute_sale_return_status(line_counts)


def lookup_sale_by_invoice(
    db: Session,
    *,
    invoice_number_raw: str | int,
    settings: Settings,
    now: datetime | None = None,
) -> SaleLookupData:
    invoice_num = parse_invoice_number(invoice_number_raw)
    if invoice_num is None:
        raise InvoiceNotFoundError("Invoice not found")

    invoice = db.scalar(select(Invoice).where(Invoice.invoice_number == invoice_num))
    if invoice is None:
        raise InvoiceNotFoundError("Invoice not found")

    sale = db.scalar(select(Sale).where(Sale.id == invoice.sale_id))
    if sale is None:
        raise InvoiceNotFoundError("Invoice not found")

    now = now or datetime.now(UTC)
    sold_at = sale.sold_at if sale.sold_at.tzinfo else sale.sold_at.replace(tzinfo=UTC)
    current_dt = now if now.tzinfo else now.replace(tzinfo=UTC)
    days_since_sale = max(
        0,
        (current_dt.astimezone(UTC).date() - sold_at.astimezone(UTC).date()).days,
    )
    requires_manager_approval = days_since_sale > settings.return_window_days

    sale_lines = db.scalars(
        select(SaleLine).where(SaleLine.sale_id == sale.id).order_by(SaleLine.id)
    ).all()

    line_counts: list[tuple[int, int]] = []
    lookup_lines: list[SaleLookupLineData] = []
    for line in sale_lines:
        item = product_stock_item(db, line.product_id, line.variant_id)
        product_name = item.product_name if item else f"Product {line.product_id}"
        sku = item.sku if item else f"SKU-{line.product_id}"
        variant_sku = item.variant_sku if item else None
        variant_attributes = item.variant_attributes if item else None

        returned_qty = int(
            db.scalar(
                select(func.coalesce(func.sum(ReturnLine.quantity), 0)).where(
                    ReturnLine.sale_line_id == line.id
                )
            )
            or 0
        )
        quantity_returnable = max(0, line.quantity - returned_qty)
        line_counts.append((line.quantity, returned_qty))

        sold_serial_ids = list(
            db.scalars(
                select(SaleLineSerial.serial_number_id).where(
                    SaleLineSerial.sale_line_id == line.id
                )
            ).all()
        )
        returned_serial_ids = set(
            db.scalars(
                select(ReturnLineSerial.serial_number_id)
                .join(ReturnLine, ReturnLine.id == ReturnLineSerial.return_line_id)
                .where(ReturnLine.sale_line_id == line.id)
            ).all()
        )
        returnable_serial_ids = [sid for sid in sold_serial_ids if sid not in returned_serial_ids]

        all_serial_labels = serial_number_labels(db, sold_serial_ids)
        serial_names = [
            all_serial_labels[sid] for sid in sold_serial_ids if sid in all_serial_labels
        ]
        returnable_serials = [
            all_serial_labels[sid] for sid in returnable_serial_ids if sid in all_serial_labels
        ]

        lookup_lines.append(
            SaleLookupLineData(
                id=line.id,
                product_id=line.product_id,
                product_name=product_name,
                sku=sku,
                variant_id=line.variant_id,
                variant_sku=variant_sku,
                variant_attributes=variant_attributes,
                quantity=line.quantity,
                unit_price=line.unit_price,
                discount_amount=line.discount_amount,
                tax_amount=line.tax_amount,
                line_total=line.line_total,
                serial_numbers=serial_names,
                quantity_returned=returned_qty,
                quantity_returnable=quantity_returnable,
                returnable_serials=returnable_serials,
                returnable_serial_ids=returnable_serial_ids,
            )
        )

    payments = list(
        db.scalars(select(Payment).where(Payment.sale_id == sale.id).order_by(Payment.id)).all()
    )
    loc_name = location_name(db, sale.location_id) or f"Location {sale.location_id}"

    return SaleLookupData(
        sale=sale,
        invoice=invoice,
        location_name=loc_name,
        lines=lookup_lines,
        payments=payments,
        days_since_sale=days_since_sale,
        return_window_days=settings.return_window_days,
        requires_manager_approval=requires_manager_approval,
        return_status=compute_sale_return_status(line_counts),
    )


def process_return(
    db: Session,
    *,
    invoice_number_raw: str | int,
    lines: list[ReturnLineInput],
    reason: str,
    processor_id: int,
    processor_username: str,
    processor_role: str,
    manager_approval: tuple[str, str] | None = None,
    settings: Settings,
    now: datetime | None = None,
) -> ReturnCreditNote:
    invoice_num = parse_invoice_number(invoice_number_raw)
    if invoice_num is None:
        raise InvoiceNotFoundError("Invoice not found")

    invoice = db.scalar(select(Invoice).where(Invoice.invoice_number == invoice_num))
    if invoice is None:
        raise InvoiceNotFoundError("Invoice not found")

    sale = db.scalar(select(Sale).where(Sale.id == invoice.sale_id).with_for_update())
    if sale is None:
        raise InvoiceNotFoundError("Invoice not found")

    reason_clean = (reason or "").strip()
    if not reason_clean:
        raise SaleInputError([{"field": "reason", "message": "Reason is required."}])
    if len(reason_clean) > 500:
        raise SaleInputError(
            [{"field": "reason", "message": "Reason must not exceed 500 characters."}]
        )

    if not lines:
        raise SaleInputError([{"field": "lines", "message": "At least one line is required."}])

    now = now or datetime.now(UTC)
    sold_at = sale.sold_at if sale.sold_at.tzinfo else sale.sold_at.replace(tzinfo=UTC)
    current_dt = now if now.tzinfo else now.replace(tzinfo=UTC)
    days_since_sale = max(
        0,
        (current_dt.astimezone(UTC).date() - sold_at.astimezone(UTC).date()).days,
    )
    is_late = days_since_sale > settings.return_window_days
    approver_id: int | None = None
    approver_username: str | None = None
    is_self_approved = False

    if is_late:
        if has_permission(processor_role, Permission.RETURNS_APPROVE_LATE):
            approver_id = processor_id
            approver_username = processor_username
            is_self_approved = True
        else:
            if not manager_approval or not manager_approval[0] or not manager_approval[1]:
                raise ReturnLateApprovalRequiredError(
                    "Manager approval is required for returns older than 30 days."
                )
            approver = verify_override(
                db,
                username=manager_approval[0],
                password=manager_approval[1],
                permission=Permission.RETURNS_APPROVE_LATE,
                actor_id=processor_id,
                actor_username=processor_username,
                settings=settings,
                now=current_dt,
            )
            approver_id = approver.id
            approver_username = approver.username
            is_self_approved = False

    # Merge duplicate lines for the same sale_line_id and condition
    merged_map: dict[tuple[int, str], tuple[int, list[int]]] = {}
    for line in lines:
        key = (line.sale_line_id, line.condition)
        prev_qty, prev_serials = merged_map.get(key, (0, []))
        merged_map[key] = (prev_qty + line.quantity, prev_serials + list(line.serial_number_ids))

    sale_lines = {
        sl.id: sl for sl in db.scalars(select(SaleLine).where(SaleLine.sale_id == sale.id)).all()
    }

    errors: list[dict[str, object]] = []
    total_requested_per_line: dict[int, int] = {}
    for (sl_id, condition), (qty, _) in merged_map.items():
        if sl_id not in sale_lines:
            errors.append(
                {
                    "line": sl_id,
                    "field": "sale_line_id",
                    "message": "Sale line does not belong to this sale.",
                }
            )
            continue
        if qty < 1:
            errors.append(
                {"line": sl_id, "field": "quantity", "message": "Quantity must be at least 1."}
            )
            continue
        if condition not in {"resaleable", "damaged"}:
            errors.append(
                {
                    "line": sl_id,
                    "field": "condition",
                    "message": "Condition must be resaleable or damaged.",
                }
            )
            continue
        total_requested_per_line[sl_id] = total_requested_per_line.get(sl_id, 0) + qty

    for sl_id, total_qty in total_requested_per_line.items():
        sl = sale_lines[sl_id]
        already_returned = int(
            db.scalar(
                select(func.coalesce(func.sum(ReturnLine.quantity), 0)).where(
                    ReturnLine.sale_line_id == sl_id
                )
            )
            or 0
        )
        returnable = sl.quantity - already_returned
        if total_qty > returnable:
            errors.append(
                {
                    "line": sl_id,
                    "field": "quantity",
                    "message": (
                        f"Requested return quantity ({total_qty}) "
                        f"exceeds returnable quantity ({returnable})."
                    ),
                }
            )

    # Validate serial tracking
    for (sl_id, _), (qty, serial_ids) in merged_map.items():
        if sl_id not in sale_lines:
            continue
        sl = sale_lines[sl_id]
        sold_serials = set(
            db.scalars(
                select(SaleLineSerial.serial_number_id).where(SaleLineSerial.sale_line_id == sl.id)
            ).all()
        )
        if sold_serials:
            returned_serials = set(
                db.scalars(
                    select(ReturnLineSerial.serial_number_id)
                    .join(ReturnLine, ReturnLine.id == ReturnLineSerial.return_line_id)
                    .where(ReturnLine.sale_line_id == sl.id)
                ).all()
            )
            returnable_serials = sold_serials - returned_serials
            if len(serial_ids) != qty:
                errors.append(
                    {
                        "line": sl_id,
                        "field": "serial_number_ids",
                        "message": f"Must provide exactly {qty} serial numbers for this line.",
                    }
                )
            elif len(serial_ids) != len(set(serial_ids)):
                errors.append(
                    {
                        "line": sl_id,
                        "field": "serial_number_ids",
                        "message": "Duplicate serial numbers provided.",
                    }
                )
            elif not set(serial_ids).issubset(returnable_serials):
                errors.append(
                    {
                        "line": sl_id,
                        "field": "serial_number_ids",
                        "message": "One or more serial numbers are not returnable.",
                    }
                )
        else:
            if serial_ids:
                errors.append(
                    {
                        "line": sl_id,
                        "field": "serial_number_ids",
                        "message": "This product is not serial-tracked.",
                    }
                )

    if errors:
        raise SaleInputError(errors)

    return_obj = Return(
        sale_id=sale.id,
        processed_by=processor_id,
        approved_by=approver_id if is_late else None,
        reason=reason_clean,
        refund_total=Decimal("0"),
    )
    db.add(return_obj)
    db.flush()

    # Process return lines sorted by (sale_line_id, condition)
    created_return_lines: list[ReturnLine] = []
    running_returned: dict[int, int] = {}
    for sl_id in total_requested_per_line:
        running_returned[sl_id] = int(
            db.scalar(
                select(func.coalesce(func.sum(ReturnLine.quantity), 0)).where(
                    ReturnLine.sale_line_id == sl_id
                )
            )
            or 0
        )

    for sl_id, condition in sorted(merged_map.keys(), key=lambda k: (k[0], k[1])):
        qty, serial_ids = merged_map[(sl_id, condition)]
        sl = sale_lines[sl_id]
        already_ret = running_returned[sl_id]
        refund = compute_line_refund(sl.line_total, sl.quantity, already_ret, qty)
        running_returned[sl_id] = already_ret + qty

        sp = sale_product(db, sl.product_id, sl.variant_id)
        is_active = (
            sp is not None and sp.product_active and (sl.variant_id is None or sp.variant_active)
        )
        restocked = condition == "resaleable" and is_active

        ret_line = ReturnLine(
            return_id=return_obj.id,
            sale_line_id=sl.id,
            quantity=qty,
            condition=condition,
            restocked=restocked,
            refund_amount=refund,
        )
        db.add(ret_line)
        db.flush()
        created_return_lines.append(ret_line)

        sold_serials = list(
            db.scalars(
                select(SaleLineSerial.serial_number_id).where(SaleLineSerial.sale_line_id == sl.id)
            ).all()
        )
        if sold_serials:
            if restocked:
                restore_returned_serials(
                    db,
                    return_line_id=ret_line.id,
                    serial_number_ids=tuple(serial_ids),
                    actor_id=processor_id,
                    actor_username=processor_username,
                )
            else:
                for sid in serial_ids:
                    db.add(ReturnLineSerial(return_line_id=ret_line.id, serial_number_id=sid))
                db.flush()
        else:
            if restocked:
                has_batch = (
                    db.scalar(
                        select(SaleLineBatch.id).where(SaleLineBatch.sale_line_id == sl.id).limit(1)
                    )
                    is not None
                )
                if has_batch:
                    restore_returned_batch_units(
                        db,
                        return_line_id=ret_line.id,
                        actor_id=processor_id,
                        actor_username=processor_username,
                    )
                else:
                    update_stock(
                        db,
                        product_id=sl.product_id,
                        variant_id=sl.variant_id,
                        location_id=sale.location_id,
                        quantity_delta=qty,
                        movement_type="return",
                        reference_type="return",
                        reference_id=return_obj.id,
                        user_id=processor_id,
                        username=processor_username,
                        record_audit=False,
                    )

    return_obj.refund_total = _money(sum(rl.refund_amount for rl in created_return_lines))

    audit_service.record(
        db,
        module="sales",
        action="return_processed",
        user_id=processor_id,
        username=processor_username,
        entity_type="return",
        entity_id=str(return_obj.id),
        details=(
            f"Processed return {return_obj.id} for sale {sale.id} "
            f"(invoice {invoice.invoice_number}) with refund {return_obj.refund_total}. "
            f"Lines: {len(created_return_lines)}."
        ),
        after={
            "return_id": return_obj.id,
            "sale_id": sale.id,
            "invoice_number": invoice.invoice_number,
            "refund_total": return_obj.refund_total,
            "lines_count": len(created_return_lines),
        },
    )

    if is_late:
        audit_service.record(
            db,
            module="sales",
            action="return_late_approved",
            user_id=approver_id,
            username=approver_username,
            entity_type="return",
            entity_id=str(return_obj.id),
            details=(
                f"Late return for sale {sale.id} (invoice {invoice.invoice_number}) "
                f"{'self-approved' if is_self_approved else 'approved'} by {approver_username}"
            ),
            after={
                "return_id": return_obj.id,
                "sale_id": sale.id,
                "invoice_number": invoice.invoice_number,
                "approver_username": approver_username,
                "processor_username": processor_username,
                "self_approved": is_self_approved,
            },
        )

    db.flush()
    return get_credit_note(db, return_obj.id)


def get_credit_note(db: Session, return_id: int) -> ReturnCreditNote:
    from fastapi import HTTPException, status

    ret = db.get(Return, return_id)
    if ret is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Return not found.")

    sale = db.scalar(select(Sale).where(Sale.id == ret.sale_id))
    if sale is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Original sale not found.")

    invoice = db.scalar(select(Invoice).where(Invoice.sale_id == sale.id))
    if invoice is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Invoice not found for sale.")

    processor_user = username_by_id(db, ret.processed_by) or f"User {ret.processed_by}"
    approver_user = username_by_id(db, ret.approved_by) if ret.approved_by else None

    return_lines = db.scalars(
        select(ReturnLine).where(ReturnLine.return_id == ret.id).order_by(ReturnLine.id)
    ).all()

    credit_lines: list[ReturnCreditNoteLine] = []
    non_sellable_qty = 0
    for rl in return_lines:
        if not rl.restocked or rl.condition == "damaged":
            non_sellable_qty += rl.quantity

        sale_line = db.get(SaleLine, rl.sale_line_id)
        if sale_line:
            item = product_stock_item(db, sale_line.product_id, sale_line.variant_id)
            p_name = item.product_name if item else f"Product {sale_line.product_id}"
            sku = item.sku if item else f"SKU-{sale_line.product_id}"
            v_sku = item.variant_sku if item else None
            p_id = sale_line.product_id
            v_id = sale_line.variant_id
        else:
            p_name = "Unknown Product"
            sku = "UNKNOWN"
            v_sku = None
            p_id = 0
            v_id = None

        ret_serial_ids = list(
            db.scalars(
                select(ReturnLineSerial.serial_number_id).where(
                    ReturnLineSerial.return_line_id == rl.id
                )
            ).all()
        )
        labels = serial_number_labels(db, ret_serial_ids)
        serial_names = [labels[sid] for sid in ret_serial_ids if sid in labels]

        credit_lines.append(
            ReturnCreditNoteLine(
                id=rl.id,
                sale_line_id=rl.sale_line_id,
                product_id=p_id,
                product_name=p_name,
                sku=sku,
                variant_id=v_id,
                variant_sku=v_sku,
                quantity=rl.quantity,
                condition=rl.condition,
                restocked=rl.restocked,
                refund_amount=rl.refund_amount,
                serial_numbers=serial_names,
            )
        )

    loc_name = location_name(db, sale.location_id) or f"Location {sale.location_id}"

    return ReturnCreditNote(
        credit_note_number=f"CN-{ret.id:04d}",
        return_id=ret.id,
        sale_id=sale.id,
        invoice_number=invoice.invoice_number,
        created_at=ret.created_at,
        sold_at=sale.sold_at,
        location_id=sale.location_id,
        location_name=loc_name,
        reason=ret.reason or "",
        processor_username=processor_user,
        approver_username=approver_user,
        refund_total=ret.refund_total,
        non_sellable_quantity=non_sellable_qty,
        lines=credit_lines,
    )


class SalesService(Protocol):
    def record(self, db: Session, **kwargs: object) -> Sale: ...
