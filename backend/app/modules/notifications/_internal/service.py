"""Stock-alert state management owned by the `notifications` module."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.notifications._internal.models import Notification, StockAlert
from app.modules.notifications.service import StockAlertData


def _alert_data(alert: StockAlert) -> StockAlertData:
    if alert.alert_type is None:
        raise ValueError("Resolved stock alerts are not active alert data.")
    return StockAlertData(
        id=alert.id,
        product_id=alert.product_id,
        variant_id=alert.variant_id,
        product_name=alert.product_name,
        sku=alert.sku,
        variant_sku=alert.variant_sku,
        location_id=alert.location_id,
        location_name=alert.location_name,
        alert_type=alert.alert_type,
        quantity=alert.quantity,
        threshold=alert.threshold,
    )


def reevaluate_stock_alert(
    db: Session,
    *,
    product_id: int,
    variant_id: int | None,
    product_name: str,
    sku: str,
    variant_sku: str | None,
    location_id: int,
    location_name: str,
    quantity: int,
    threshold: int,
) -> StockAlertData | None:
    """Update the current alert for an item/location; the caller owns the transaction."""
    if quantity < 0 or threshold < 0:
        raise ValueError("Stock quantity and threshold must be nonnegative.")

    alert_type = "out_of_stock" if quantity == 0 else "low_stock" if quantity <= threshold else None
    alert = db.scalar(
        select(StockAlert)
        .where(
            StockAlert.product_id == product_id,
            StockAlert.variant_id.is_not_distinct_from(variant_id),
            StockAlert.location_id == location_id,
        )
        .with_for_update()
    )
    if alert is None and alert_type is None:
        return None
    if alert is None:
        alert = StockAlert(
            product_id=product_id,
            variant_id=variant_id,
            location_id=location_id,
            product_name=product_name,
            sku=sku,
            variant_sku=variant_sku,
            location_name=location_name,
            quantity=quantity,
            threshold=threshold,
            alert_type=alert_type,
        )
        db.add(alert)
    else:
        was_active = alert.alert_type is not None
        alert.product_name = product_name
        alert.sku = sku
        alert.variant_sku = variant_sku
        alert.location_name = location_name
        alert.quantity = quantity
        alert.threshold = threshold
        alert.alert_type = alert_type
        if alert_type is not None:
            alert.resolved_at = None
        elif was_active:
            alert.resolved_at = datetime.now(UTC)

    db.flush()
    return _alert_data(alert) if alert_type is not None else None


def active_stock_alerts(db: Session, *, location_id: int | None = None) -> list[StockAlertData]:
    query = select(StockAlert).where(StockAlert.alert_type.is_not(None))
    if location_id is not None:
        query = query.where(StockAlert.location_id == location_id)
    return [
        _alert_data(alert)
        for alert in db.scalars(
            query.order_by(StockAlert.location_name, StockAlert.product_name, StockAlert.id)
        )
    ]


def record_purchase_order_status(
    db: Session,
    *,
    recipient_ids: list[int],
    purchase_order_id: int,
    po_number: str,
    status: str,
) -> None:
    """Add one in-app notification per recipient in the caller's transaction."""
    if status not in {"submitted", "partially_received", "received", "cancelled"}:
        raise ValueError(f"Unsupported purchase order notification status: {status}.")
    for recipient_id in set(recipient_ids):
        db.add(
            Notification(
                recipient_user_id=recipient_id,
                type="po_status",
                title="Purchase order status changed",
                message=f"{po_number}: {status.replace('_', ' ').title()}",
                location_id=None,
                reference_type="purchase_order",
                reference_id=purchase_order_id,
            )
        )
    db.flush()
