"""Public service interface of the `reporting` module."""

from decimal import Decimal
from typing import Protocol

from sqlalchemy.orm import Session

from app.modules.stock import StockPosition


class ReportingService(Protocol):
    """Operations the `reporting` module offers to other modules.

    Methods are added as features land; callers depend on this interface,
    never on `_internal`.
    """


def valuation_rows(
    db: Session, *, location_id: int | None = None
) -> tuple[list[tuple[StockPosition, Decimal]], Decimal]:
    """Return live stock positions and their quantity-times-average-cost values."""
    from app.modules.stock import stock_positions

    rows = []
    total = Decimal(0)
    for position in stock_positions(db, location_id=location_id):
        value = (position.average_cost or Decimal(0)) * position.quantity
        rows.append((position, value))
        total += value
    return rows, total


def reorder_rows(db: Session, *, location_id: int | None = None) -> list[tuple[StockPosition, int]]:
    """Return at/below-threshold stock and its needed quantity to reach reorder-to."""
    from app.modules.stock import stock_positions

    return [
        (position, max(position.reorder_to_level - position.quantity, 0))
        for position in stock_positions(db, location_id=location_id)
        if position.quantity <= position.reorder_threshold
    ]
