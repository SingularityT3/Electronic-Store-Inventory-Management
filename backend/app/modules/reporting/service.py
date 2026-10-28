"""Public service interface of the `reporting` module."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from sqlalchemy.orm import Session

from app.modules.purchasing import supplier_catalog_costs
from app.modules.stock import StockPosition


@dataclass(frozen=True)
class ValuationRow:
    position: StockPosition
    unit_cost: Decimal
    value: Decimal
    cost_not_set: bool


class ReportingService(Protocol):
    """Operations the `reporting` module offers to other modules.

    Methods are added as features land; callers depend on this interface,
    never on `_internal`.
    """


def valuation_rows(
    db: Session, *, location_id: int | None = None
) -> tuple[list[ValuationRow], Decimal]:
    """Return live values using average cost, then active supplier catalog price."""
    from app.modules.stock import stock_positions

    positions = stock_positions(db, location_id=location_id)
    missing_cost_keys = {
        (position.product_id, position.variant_id)
        for position in positions
        if position.average_cost is None
    }
    catalog_costs = supplier_catalog_costs(db, product_keys=tuple(missing_cost_keys))

    rows = []
    total = Decimal(0)
    for position in positions:
        key = (position.product_id, position.variant_id)
        catalog_cost = catalog_costs.get(key)
        cost_not_set = position.average_cost is None and catalog_cost is None
        if position.average_cost is not None:
            unit_cost = position.average_cost
        elif catalog_cost is not None:
            unit_cost = catalog_cost
        else:
            unit_cost = Decimal(0)
        value = unit_cost * position.quantity
        rows.append(ValuationRow(position, unit_cost, value, cost_not_set))
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
