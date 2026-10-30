"""In-app low-stock and order status notifications.

Public surface of the `notifications` module. Other modules may import from here only;
`_internal` is private to this module.
"""

from app.modules.notifications._internal.service import (
    active_stock_alerts,
    alerted_product_ids,
    record_purchase_order_status,
    reevaluate_stock_alert,
    resolve_stock_alerts,
)
from app.modules.notifications.service import NotificationsService, StockAlertData

__all__ = [
    "NotificationsService",
    "StockAlertData",
    "active_stock_alerts",
    "alerted_product_ids",
    "reevaluate_stock_alert",
    "record_purchase_order_status",
    "resolve_stock_alerts",
]
