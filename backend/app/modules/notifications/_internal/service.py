"""Stock-alert state management and notification lifecycle owned by the `notifications` module."""

from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import false, or_, select
from sqlalchemy.orm import Session

from app.modules.auth import stock_alert_notification_recipients
from app.modules.notifications._internal.models import Notification, StockAlert
from app.modules.notifications.service import NotificationData, StockAlertData


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


def _notification_data(notification: Notification) -> NotificationData:
    return NotificationData(
        id=notification.id,
        recipient_user_id=notification.recipient_user_id,
        type=notification.type,
        title=notification.title,
        message=notification.message,
        location_id=notification.location_id,
        location_name=None,  # Will be set by caller if needed
        reference_type=notification.reference_type,
        reference_id=notification.reference_id,
        is_read=notification.is_read,
        read_at=notification.read_at,
        dismissed_at=notification.dismissed_at,
        resolved_at=notification.resolved_at,
        created_at=notification.created_at,
    )


def _create_stock_notification(
    db: Session,
    *,
    recipient_id: int,
    alert_type: str,
    product_name: str,
    sku: str,
    variant_sku: str | None,
    location_id: int,
    location_name: str,
    quantity: int,
    threshold: int,
    stock_alert_id: int,
) -> Notification:
    """Create a stock notification for a recipient."""
    title = f"{'Low stock' if alert_type == 'low_stock' else 'Out of stock'}: {product_name}"
    if variant_sku:
        title += f" ({variant_sku})"

    if alert_type == "low_stock":
        message = (
            f"Low stock: {product_name} (SKU: {sku}) at {location_name}. "
            f"Current quantity: {quantity}. Reorder level: {threshold}."
        )
    else:
        message = (
            f"Out of stock: {product_name} (SKU: {sku}) at {location_name}. "
            f"Current quantity: 0."
        )

    notification = Notification(
        recipient_user_id=recipient_id,
        type=alert_type,
        title=title,
        message=message,
        location_id=location_id,
        reference_type="stock_alert",
        reference_id=stock_alert_id,
    )
    db.add(notification)
    return notification


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
    """Update the current alert for an item/location; the caller owns the transaction.
    Also manages notification lifecycle in the same transaction."""
    if quantity < 0 or threshold < 0:
        raise ValueError("Stock quantity and threshold must be nonnegative.")

    # Determine new alert type
    new_alert_type = (
        "out_of_stock" if quantity == 0 else "low_stock" if quantity <= threshold else None
    )

    # Get or create stock alert row
    alert = db.scalar(
        select(StockAlert)
        .where(
            StockAlert.product_id == product_id,
            StockAlert.variant_id.is_not_distinct_from(variant_id),
            StockAlert.location_id == location_id,
        )
        .with_for_update()
    )

    # If no alert row and no new alert type, nothing to do
    if alert is None and new_alert_type is None:
        return None

    # Get recipients for this location
    recipients = stock_alert_notification_recipients(db, location_id=location_id)

    if alert is None:
        # New alert row
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
            alert_type=new_alert_type,
        )
        db.add(alert)
        db.flush()  # Get the alert ID

        # Create notifications for new alert
        if new_alert_type is not None:
            for recipient_id in recipients:
                _create_stock_notification(
                    db,
                    recipient_id=recipient_id,
                    alert_type=new_alert_type,
                    product_name=product_name,
                    sku=sku,
                    variant_sku=variant_sku,
                    location_id=location_id,
                    location_name=location_name,
                    quantity=quantity,
                    threshold=threshold,
                    stock_alert_id=alert.id,
                )
    else:
        # Existing alert row
        old_alert_type = alert.alert_type

        # Update alert row
        was_active = alert.alert_type is not None
        alert.product_name = product_name
        alert.sku = sku
        alert.variant_sku = variant_sku
        alert.location_name = location_name
        alert.quantity = quantity
        alert.threshold = threshold
        alert.alert_type = new_alert_type

        if new_alert_type is not None:
            alert.resolved_at = None
        elif was_active:
            alert.resolved_at = datetime.now(UTC)

        db.flush()

        # Handle notification lifecycle
        if new_alert_type is None:
            # Alert resolved - mark all active notifications for this alert as resolved
            if old_alert_type is not None:
                db.execute(
                    Notification.__table__.update()
                    .where(
                        Notification.reference_type == "stock_alert",
                        Notification.reference_id == alert.id,
                        Notification.dismissed_at.is_(None),
                        Notification.resolved_at.is_(None),
                    )
                    .values(resolved_at=datetime.now(UTC))
                )
        elif old_alert_type is None:
            # New alert (was resolved, now active)
            for recipient_id in recipients:
                _create_stock_notification(
                    db,
                    recipient_id=recipient_id,
                    alert_type=new_alert_type,
                    product_name=product_name,
                    sku=sku,
                    variant_sku=variant_sku,
                    location_id=location_id,
                    location_name=location_name,
                    quantity=quantity,
                    threshold=threshold,
                    stock_alert_id=alert.id,
                )
        elif new_alert_type != old_alert_type:
            # Alert type changed (low <-> out of stock)
            # Resolve old notifications
            db.execute(
                Notification.__table__.update()
                .where(
                    Notification.reference_type == "stock_alert",
                    Notification.reference_id == alert.id,
                    Notification.dismissed_at.is_(None),
                    Notification.resolved_at.is_(None),
                )
                .values(resolved_at=datetime.now(UTC))
            )
            # Create new notifications for new type
            for recipient_id in recipients:
                _create_stock_notification(
                    db,
                    recipient_id=recipient_id,
                    alert_type=new_alert_type,
                    product_name=product_name,
                    sku=sku,
                    variant_sku=variant_sku,
                    location_id=location_id,
                    location_name=location_name,
                    quantity=quantity,
                    threshold=threshold,
                    stock_alert_id=alert.id,
                )
        else:
            # Same alert type, but quantity may have changed
            # Update message of existing non-dismissed, non-resolved notifications
            notifications = db.scalars(
                select(Notification).where(
                    Notification.reference_type == "stock_alert",
                    Notification.reference_id == alert.id,
                    Notification.dismissed_at.is_(None),
                    Notification.resolved_at.is_(None),
                )
            ).all()
            if new_alert_type == "low_stock":
                new_message = (
                    f"Low stock: {product_name} (SKU: {sku}) at {location_name}. "
                    f"Current quantity: {quantity}. Reorder level: {threshold}."
                )
            else:
                new_message = (
                    f"Out of stock: {product_name} (SKU: {sku}) at {location_name}. "
                    f"Current quantity: 0."
                )
            for n in notifications:
                n.message = new_message

    return _alert_data(alert) if new_alert_type is not None else None


def resolve_stock_alerts(
    db: Session, *, product_id: int, variant_ids: Iterable[int | None] | None = None
) -> None:
    """Clear the alerts of items that no longer hold stock: a deleted product (all its items,
    when `variant_ids` is None), deleted variants, or a base product that gained variants."""
    query = select(StockAlert).where(
        StockAlert.product_id == product_id, StockAlert.alert_type.is_not(None)
    )
    if variant_ids is not None:
        ids = list(variant_ids)
        query = query.where(
            or_(
                StockAlert.variant_id.in_([i for i in ids if i is not None]),
                StockAlert.variant_id.is_(None) if None in ids else false(),
            )
        )
    now = datetime.now(UTC)
    for alert in db.scalars(query.with_for_update()):
        alert.alert_type = None
        alert.resolved_at = now
        # Also mark notifications as resolved
        db.execute(
            Notification.__table__.update()
            .where(
                Notification.reference_type == "stock_alert",
                Notification.reference_id == alert.id,
                Notification.dismissed_at.is_(None),
                Notification.resolved_at.is_(None),
            )
            .values(resolved_at=now)
        )
    db.flush()


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


def alerted_product_ids(db: Session, *, location_id: int | None = None) -> set[int]:
    """Ids of products with an active alert; reads one column, for catalogue-wide filters."""
    query = select(StockAlert.product_id).where(StockAlert.alert_type.is_not(None)).distinct()
    if location_id is not None:
        query = query.where(StockAlert.location_id == location_id)
    return set(db.scalars(query))


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


# --- New notification API functions ---


def list_user_notifications(
    db: Session,
    *,
    user_id: int,
    limit: int = 20,
    offset: int = 0,
    unread_only: bool = False,
    include_read: bool = True,
) -> list[NotificationData]:
    """List active notifications for a user (dismissed_at IS NULL AND resolved_at IS NULL).
    Newest first."""
    if limit > 100:
        limit = 100

    query = select(Notification).where(
        Notification.recipient_user_id == user_id,
        Notification.dismissed_at.is_(None),
        Notification.resolved_at.is_(None),
    )

    if unread_only:
        query = query.where(Notification.is_read.is_(False))
    elif not include_read:
        query = query.where(Notification.is_read.is_(True))

    query = query.order_by(Notification.created_at.desc()).offset(offset).limit(limit)

    return [_notification_data(n) for n in db.scalars(query)]


def unread_count(db: Session, *, user_id: int) -> int:
    """Count unread active notifications for a user."""
    return (
        db.scalar(
            select(select(Notification.id))
            .where(
                Notification.recipient_user_id == user_id,
                Notification.dismissed_at.is_(None),
                Notification.resolved_at.is_(None),
                Notification.is_read.is_(False),
            )
            .exists()
            .select()
        )
        or 0
    )


def mark_read(db: Session, *, user_id: int, notification_id: int) -> None:
    """Mark a notification as read. Idempotent. 404 if not found or not owned by user."""
    notification = db.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.recipient_user_id == user_id,
            Notification.dismissed_at.is_(None),
            Notification.resolved_at.is_(None),
        )
    )
    if notification is None:
        raise ValueError("Notification not found")
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = datetime.now(UTC)
    db.flush()


def mark_all_read(db: Session, *, user_id: int) -> None:
    """Mark all active notifications as read for a user. Idempotent."""
    now = datetime.now(UTC)
    db.execute(
        Notification.__table__.update()
        .where(
            Notification.recipient_user_id == user_id,
            Notification.dismissed_at.is_(None),
            Notification.resolved_at.is_(None),
            Notification.is_read.is_(False),
        )
        .values(is_read=True, read_at=now)
    )
    db.flush()


def dismiss(db: Session, *, user_id: int, notification_id: int) -> None:
    """Dismiss a notification (also marks as read). Idempotent.

    404 if not found or not owned by user.
    """
    notification = db.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.recipient_user_id == user_id,
            Notification.dismissed_at.is_(None),
            Notification.resolved_at.is_(None),
        )
    )
    if notification is None:
        raise ValueError("Notification not found")
    if notification.dismissed_at is None:
        notification.dismissed_at = datetime.now(UTC)
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = datetime.now(UTC)
    db.flush()
