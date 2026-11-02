"""Public service interface of the `purchasing` module."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.audit import audit_service
from app.modules.auth import po_status_notification_recipients
from app.modules.notifications import record_purchase_order_status
from app.modules.purchasing._internal.models import (
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseOrderReceipt,
    PurchaseOrderReceiptLine,
    Supplier,
    SupplierPriceHistory,
    SupplierProduct,
)


class PurchasingService(Protocol):
    """Operations the `purchasing` module offers to other modules.

    Methods are added as features land; callers depend on this interface,
    never on `_internal`.
    """


@dataclass(frozen=True)
class SupplierReportSupplier:
    id: int
    name: str


@dataclass(frozen=True)
class SupplierReportOrder:
    supplier_id: int
    created_at: datetime
    expected_delivery_date: date | None
    first_receipt_at: datetime | None
    order_value: Decimal
    quantity_ordered: int
    quantity_accepted: int


@dataclass(frozen=True)
class SupplierReportPrice:
    supplier_id: int
    product_id: int
    variant_id: int | None
    unit_price: Decimal
    recorded_at: datetime


def supplier_report_sources(
    db: Session,
    *,
    start: datetime,
    end: datetime,
    supplier_ids: Sequence[int] | None = None,
) -> tuple[list[SupplierReportSupplier], list[SupplierReportOrder], list[SupplierReportPrice]]:
    """Return period-bounded report data; partial receipts remain one PO delivery."""
    supplier_query = select(Supplier.id, Supplier.name).order_by(Supplier.name, Supplier.id)
    if supplier_ids is not None:
        supplier_query = supplier_query.where(Supplier.id.in_(supplier_ids))
    suppliers = [
        SupplierReportSupplier(id=supplier_id, name=name)
        for supplier_id, name in db.execute(supplier_query)
    ]
    selected_ids = [supplier.id for supplier in suppliers]
    if not selected_ids:
        return suppliers, [], []

    accepted_by_line = (
        select(
            PurchaseOrderReceiptLine.po_line_id.label("po_line_id"),
            func.sum(PurchaseOrderReceiptLine.quantity_accepted).label("quantity_accepted"),
        )
        .group_by(PurchaseOrderReceiptLine.po_line_id)
        .subquery()
    )
    line_totals = (
        select(
            PurchaseOrderLine.purchase_order_id.label("purchase_order_id"),
            func.sum(PurchaseOrderLine.quantity_ordered * PurchaseOrderLine.unit_price).label(
                "order_value"
            ),
            func.sum(PurchaseOrderLine.quantity_ordered).label("quantity_ordered"),
            func.sum(func.coalesce(accepted_by_line.c.quantity_accepted, 0)).label(
                "quantity_accepted"
            ),
        )
        .outerjoin(accepted_by_line, accepted_by_line.c.po_line_id == PurchaseOrderLine.id)
        .group_by(PurchaseOrderLine.purchase_order_id)
        .subquery()
    )
    # A PO has one delivery date in this metric, even when receiving records several partials.
    first_receipts = (
        select(
            PurchaseOrderReceipt.purchase_order_id.label("purchase_order_id"),
            func.min(PurchaseOrderReceipt.received_at).label("first_receipt_at"),
        )
        .group_by(PurchaseOrderReceipt.purchase_order_id)
        .subquery()
    )
    order_rows = db.execute(
        select(
            PurchaseOrder.supplier_id,
            PurchaseOrder.created_at,
            PurchaseOrder.expected_delivery_date,
            first_receipts.c.first_receipt_at,
            func.coalesce(line_totals.c.order_value, Decimal("0")),
            func.coalesce(line_totals.c.quantity_ordered, 0),
            func.coalesce(line_totals.c.quantity_accepted, 0),
        )
        .outerjoin(line_totals, line_totals.c.purchase_order_id == PurchaseOrder.id)
        .outerjoin(first_receipts, first_receipts.c.purchase_order_id == PurchaseOrder.id)
        .where(
            PurchaseOrder.supplier_id.in_(selected_ids),
            PurchaseOrder.created_at >= start,
            PurchaseOrder.created_at < end,
            PurchaseOrder.status.in_(("submitted", "partially_received", "received")),
        )
        .order_by(PurchaseOrder.supplier_id, PurchaseOrder.created_at, PurchaseOrder.id)
    )
    orders = [
        SupplierReportOrder(
            supplier_id=supplier_id,
            created_at=created_at,
            expected_delivery_date=expected_delivery_date,
            first_receipt_at=first_receipt_at,
            order_value=order_value,
            quantity_ordered=quantity_ordered,
            quantity_accepted=quantity_accepted,
        )
        for (
            supplier_id,
            created_at,
            expected_delivery_date,
            first_receipt_at,
            order_value,
            quantity_ordered,
            quantity_accepted,
        ) in order_rows
    ]

    price_rows = db.execute(
        select(
            SupplierPriceHistory.supplier_id,
            SupplierPriceHistory.product_id,
            SupplierPriceHistory.variant_id,
            SupplierPriceHistory.unit_price,
            SupplierPriceHistory.recorded_at,
        )
        .where(
            SupplierPriceHistory.supplier_id.in_(selected_ids),
            SupplierPriceHistory.recorded_at >= start,
            SupplierPriceHistory.recorded_at < end,
        )
        .order_by(
            SupplierPriceHistory.supplier_id,
            SupplierPriceHistory.product_id,
            SupplierPriceHistory.variant_id,
            SupplierPriceHistory.recorded_at,
            SupplierPriceHistory.id,
        )
    )
    prices = [
        SupplierReportPrice(
            supplier_id=supplier_id,
            product_id=product_id,
            variant_id=variant_id,
            unit_price=unit_price,
            recorded_at=recorded_at,
        )
        for supplier_id, product_id, variant_id, unit_price, recorded_at in price_rows
    ]
    return suppliers, orders, prices


def supplier_catalog_costs(
    db: Session, *, product_keys: Sequence[tuple[int, int | None]]
) -> dict[tuple[int, int | None], Decimal]:
    """Return the lowest current catalog price from an active supplier per item."""
    keys = set(product_keys)
    if not keys:
        return {}

    product_ids = {product_id for product_id, _ in keys}
    rows = db.execute(
        select(
            SupplierProduct.product_id,
            SupplierProduct.variant_id,
            func.min(SupplierProduct.supplier_price),
        )
        .join(Supplier, Supplier.id == SupplierProduct.supplier_id)
        .where(Supplier.is_active, SupplierProduct.product_id.in_(product_ids))
        .group_by(SupplierProduct.product_id, SupplierProduct.variant_id)
    )
    return {
        (product_id, variant_id): price
        for product_id, variant_id, price in rows
        if (product_id, variant_id) in keys
    }


def update_purchase_order_receipt_status(
    db: Session,
    *,
    purchase_order_id: int,
    actor_id: int,
    actor_username: str,
) -> str:
    """Reconcile PO status after receipt lines change, inside the receipt transaction."""
    order = db.scalar(
        select(PurchaseOrder).where(PurchaseOrder.id == purchase_order_id).with_for_update()
    )
    if order is None:
        raise LookupError("Purchase order not found.")
    if order.status not in {"submitted", "partially_received"}:
        raise ValueError(f"Cannot receive purchase order with status {order.status}.")

    lines = db.scalars(
        select(PurchaseOrderLine)
        .where(PurchaseOrderLine.purchase_order_id == purchase_order_id)
        .with_for_update()
    ).all()
    if not lines:
        raise ValueError("Purchase order has no lines.")

    has_received_quantity = any(line.quantity_received > 0 for line in lines)
    if not has_received_quantity:
        return order.status

    new_status = (
        "received"
        if all(line.quantity_received == line.quantity_ordered for line in lines)
        else "partially_received"
    )
    if order.status == new_status:
        return order.status

    previous_status = order.status
    order.status = new_status
    audit_service.record(
        db,
        module="purchasing",
        action="purchase_order_status_changed",
        user_id=actor_id,
        username=actor_username,
        entity_type="purchase_order",
        entity_id=str(order.id),
        before={"status": previous_status},
        after={"status": new_status},
    )
    record_purchase_order_status(
        db,
        recipient_ids=po_status_notification_recipients(db, created_by_id=order.created_by),
        purchase_order_id=order.id,
        po_number=order.po_number,
        status=new_status,
    )
    db.flush()
    return new_status
