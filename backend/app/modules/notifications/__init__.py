"""In-app low-stock and order status notifications.

Public surface of the `notifications` module. Other modules may import from here only;
`_internal` is private to this module.
"""

from app.modules.notifications.service import NotificationsService

__all__ = ["NotificationsService"]
