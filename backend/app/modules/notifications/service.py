"""Public service interface of the `notifications` module."""

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import Session


@dataclass(frozen=True)
class StockAlertData:
    id: int
    product_id: int
    variant_id: int | None
    product_name: str
    sku: str
    variant_sku: str | None
    location_id: int
    location_name: str
    alert_type: str
    quantity: int
    threshold: int


@dataclass(frozen=True)
class NotificationData:
    id: int
    recipient_user_id: int
    type: str
    title: str
    message: str
    location_id: int | None
    location_name: str | None
    reference_type: str | None
    reference_id: int | None
    is_read: bool
    read_at: object | None
    dismissed_at: object | None
    resolved_at: object | None
    created_at: object


class NotificationsService(Protocol):
    """Operations the `notifications` module offers to other modules.

    Methods are added as features land; callers depend on this interface,
    never on `_internal`.
    """

    def reevaluate_stock_alert(
        self,
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
    ) -> StockAlertData | None: ...

    def active_stock_alerts(
        self, db: Session, *, location_id: int | None = None
    ) -> list[StockAlertData]: ...

    def alerted_product_ids(self, db: Session, *, location_id: int | None = None) -> set[int]: ...

    def resolve_stock_alerts(
        self, db: Session, *, product_id: int, variant_ids: list[int | None] | None = None
    ) -> None: ...

    def record_purchase_order_status(
        self,
        db: Session,
        *,
        recipient_ids: list[int],
        purchase_order_id: int,
        po_number: str,
        status: str,
    ) -> None: ...

    def list_user_notifications(
        self,
        db: Session,
        *,
        user_id: int,
        limit: int = 20,
        offset: int = 0,
        unread_only: bool = False,
        include_read: bool = True,
    ) -> list[NotificationData]: ...

    def unread_count(self, db: Session, *, user_id: int) -> int: ...

    def mark_read(self, db: Session, *, user_id: int, notification_id: int) -> None: ...

    def mark_all_read(self, db: Session, *, user_id: int) -> None: ...

    def dismiss(self, db: Session, *, user_id: int, notification_id: int) -> None: ...
