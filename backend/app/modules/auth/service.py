"""Public service interface of the `auth` module."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.modules.auth._internal.models import User


class Permission(StrEnum):
    """What a role may do (FR-5.1, SEC-AZ-1). Routes declare one with `require(...)`.

    Which roles hold which permission is the matrix in `_internal/permissions.py`.
    """

    USERS_MANAGE = "users.manage"
    AUDIT_VIEW = "audit.view"
    PRODUCTS_VIEW = "products.view"
    """Product search and listing."""
    PRODUCTS_MANAGE = "products.manage"
    """Create and edit products, categories and variants, including prices."""
    STOCK_VIEW = "stock.view"
    LOCATIONS_MANAGE = "locations.manage"
    STOCK_ADJUST = "stock.adjust"
    STOCK_TRANSFER = "stock.transfer"
    SUPPLIERS_MANAGE = "suppliers.manage"
    """Suppliers and supplier price history."""
    PURCHASE_ORDERS_MANAGE = "purchase_orders.manage"
    PURCHASE_ORDERS_RECEIVE = "purchase_orders.receive"
    SALES_RECORD = "sales.record"
    """Record sales and returns."""
    RETURNS_APPROVE_LATE = "returns.approve_late"
    """Approve a return older than 30 days (Manager override, SRS A-11)."""
    REPORTS_VIEW = "reports.view"
    """Reports and CSV/PDF exports."""
    NOTIFICATIONS_VIEW = "notifications.view"


@dataclass(frozen=True)
class CurrentUser:
    """The signed-in user of a request, as given by the `current_user` dependency."""

    id: int
    username: str
    full_name: str
    role: str
    location_id: int | None

    @property
    def sees_all_locations(self) -> bool:
        """Staff and Cashier see only their own location; Manager and Admin see all (SRS A-9)."""
        return self.role in ("admin", "manager")


class AuthService(Protocol):
    """Operations the `auth` module offers to other modules.

    Methods are added as features land; callers depend on this interface,
    never on `_internal`. Routes get the signed-in user from the `current_user`
    dependency exported by this module.
    """


class LocationValidator(Protocol):
    """Composition-root supplied validation for stock-owned locations."""

    def __call__(self, db: Session, location_id: int) -> bool: ...


def po_status_notification_recipients(db: Session, *, created_by_id: int) -> list[int]:
    """Return Admins and the Manager who created a PO for its status notifications."""
    recipient_ids = db.scalars(
        select(User.id).where(
            User.is_active,
            or_(User.role == "admin", User.id == created_by_id),
        )
    ).all()
    creator_role = db.scalar(select(User.role).where(User.id == created_by_id))
    if creator_role != "manager":
        recipient_ids = [user_id for user_id in recipient_ids if user_id != created_by_id]
    return list(recipient_ids)
