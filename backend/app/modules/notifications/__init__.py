"""In-app low-stock and order status notifications.

Public surface of the `notifications` module. Other modules may import from here only;
`_internal` is private to this module.
"""

from app.modules.notifications._internal.service import (
    active_stock_alerts,
    alerted_product_ids,
    dismiss,
    list_user_notifications,
    mark_all_read,
    mark_read,
    record_purchase_order_status,
    reevaluate_stock_alert,
    resolve_stock_alerts,
    unread_count,
)
from app.modules.notifications.service import (
    NotificationData,
    NotificationsService,
    StockAlertData,
)

__all__ = [
    "NotificationsService",
    "NotificationData",
    "StockAlertData",
    "active_stock_alerts",
    "alerted_product_ids",
    "dismiss",
    "list_user_notifications",
    "mark_all_read",
    "mark_read",
    "reevaluate_stock_alert",
    "record_purchase_order_status",
    "resolve_stock_alerts",
    "unread_count",
]
