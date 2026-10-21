"""Public service interface of the `stock` module."""

from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.stock._internal.models import Location


class StockService(Protocol):
    """Operations the `stock` module offers to other modules.

    Methods are added as features land; callers depend on this interface,
    never on `_internal`.
    """


def location_exists(db: Session, location_id: int) -> bool:
    """Validate a location without exposing the stock table to auth."""
    return (
        db.scalar(select(Location.id).where(Location.id == location_id, Location.is_active))
        is not None
    )
