"""Public service interface of the `purchasing` module."""

from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.audit import audit_service
from app.modules.auth import po_status_notification_recipients
from app.modules.notifications import record_purchase_order_status
from app.modules.purchasing._internal.models import (
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseOrderReceipt,
)


class PurchasingService(Protocol):
    """Operations the `purchasing` module offers to other modules.

    Methods are added as features land; callers depend on this interface,
    never on `_internal`.
    """


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

    receipt_started = db.scalar(
        select(PurchaseOrderReceipt.id)
        .where(PurchaseOrderReceipt.purchase_order_id == purchase_order_id)
        .limit(1)
    )
    has_received_quantity = any(line.quantity_received > 0 for line in lines)
    if receipt_started is None and not has_received_quantity:
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
