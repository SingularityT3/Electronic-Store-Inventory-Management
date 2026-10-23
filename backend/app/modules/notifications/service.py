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
