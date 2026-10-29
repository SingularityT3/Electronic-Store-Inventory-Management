"""Public service interface of the `reporting` module."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from sqlalchemy.orm import Session

from app.modules.purchasing import supplier_catalog_costs
from app.modules.reporting._internal.export import ReportTable
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


def _variant_label(position: StockPosition) -> str:
    attributes = (
        ", ".join(f"{name}: {value}" for name, value in position.variant_attributes.items())
        if position.variant_attributes
        else ""
    )
    return " — ".join(part for part in (position.variant_sku, attributes) if part) or "—"


def _location_filter(db: Session, location_id: int | None) -> dict[str, str]:
    from app.modules.stock import location_name

    if location_id is None:
        return {"Location": "All locations"}
    return {"Location": location_name(db, location_id) or str(location_id)}


def valuation_table(db: Session, *, location_id: int | None = None) -> ReportTable:
    """The stock valuation report as shown on screen, ready to export."""
    rows, total = valuation_rows(db, location_id=location_id)
    return ReportTable(
        title="Stock Valuation Report",
        columns=[
            "Product / SKU",
            "Variant",
            "Location",
            "Quantity",
            "Unit cost",
            "Inventory value",
        ],
        rows=[
            [
                f"{row.position.product_name} ({row.position.sku})",
                _variant_label(row.position),
                row.position.location_name,
                str(row.position.quantity),
                "Cost not set" if row.cost_not_set else f"{row.unit_cost:.4f}",
                f"{row.value:.2f}",
            ]
            for row in rows
        ],
        filters=_location_filter(db, location_id),
        summary={"Total inventory value": f"{total:.2f}"},
        widths=[4, 3, 2.5, 1.2, 1.5, 1.8],
    )


def reorder_table(db: Session, *, location_id: int | None = None) -> ReportTable:
    """The reorder report as returned by the API, ready to export."""
    return ReportTable(
        title="Reorder Report",
        columns=[
            "Product / SKU",
            "Variant",
            "Location",
            "Quantity",
            "Reorder threshold",
            "Reorder-to level",
            "Suggested quantity",
        ],
        rows=[
            [
                f"{position.product_name} ({position.sku})",
                _variant_label(position),
                position.location_name,
                str(position.quantity),
                str(position.reorder_threshold),
                str(position.reorder_to_level),
                str(suggested),
            ]
            for position, suggested in reorder_rows(db, location_id=location_id)
        ],
        filters=_location_filter(db, location_id),
        widths=[4, 3, 2.5, 1.2, 1.5, 1.5, 1.5],
    )
