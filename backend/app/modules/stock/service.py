
"""Public service interface of the `stock` module."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.modules.product import ProductStockItem, product_stock_items
from app.modules.stock._internal.models import (
    ItemCost,
    Location,
    SerialNumber,
    StockLevel,
)


@dataclass(frozen=True)
class StockPosition:
    """A stock quantity and its display/reorder/valuation data for one active location."""

    product_id: int
    product_name: str
    sku: str
    category_id: int
    category_name: str
    variant_id: int | None
    variant_sku: str | None
    variant_attributes: dict[str, object] | None
    location_id: int
    location_name: str
    quantity: int
    reorder_threshold: int
    reorder_to_level: int
    average_cost: Decimal | None


def stock_positions(
    db: Session, *, location_id: int | None = None
) -> list[StockPosition]:
    """Read live stock with product metadata and cost through owning module interfaces."""
    query = (
        select(StockLevel, Location.name)
        .join(Location, Location.id == StockLevel.location_id)
        .where(Location.is_active)
    )
    if location_id is not None:
        query = query.where(StockLevel.location_id == location_id)

    item_metadata: dict[tuple[int, int | None], ProductStockItem] = {
        (item.product_id, item.variant_id): item for item in product_stock_items(db)
    }
    costs = {
        (product_id, variant_id): average_cost
        for product_id, variant_id, average_cost in db.execute(
            select(ItemCost.product_id, ItemCost.variant_id, ItemCost.average_cost)
        )
    }

    positions = []
    for level, location_name in db.execute(
        query.order_by(Location.name, StockLevel.id)
    ):
        key = (level.product_id, level.variant_id)
        item = item_metadata.get(key)
        if item is None:
            raise RuntimeError(f"Missing product metadata for stock item {key}.")

        positions.append(
            StockPosition(
                product_id=item.product_id,
                product_name=item.product_name,
                sku=item.sku,
                category_id=item.category_id,
                category_name=item.category_name,
                variant_id=item.variant_id,
                variant_sku=item.variant_sku,
                variant_attributes=item.variant_attributes,
                location_id=level.location_id,
                location_name=location_name,
                quantity=level.quantity,
                reorder_threshold=level.reorder_threshold,
                reorder_to_level=(
                    level.reorder_to_level
                    if level.reorder_to_level is not None
                    else 2 * level.reorder_threshold
                ),
                average_cost=costs.get(key),
            )
        )

    return positions


class StockService(Protocol):
    """Operations the `stock` module offers to other modules.

    Methods are added as features land; callers depend on this interface,
    never on `_internal`.
    """

    def positions(
        self, db: Session, *, location_id: int | None = None
    ) -> list[StockPosition]: ...


def has_stock(db: Session, product_id: int) -> bool:
    """Return whether a product or variant has stock on hand."""
    return bool(
        db.scalar(
            select(
                exists().where(
                    StockLevel.product_id == product_id,
                    StockLevel.quantity > 0,
                )
            )
        )
        or db.scalar(
            select(
                exists().where(
                    SerialNumber.product_id == product_id,
                    SerialNumber.status == "in_stock",
                )
            )
        )
    )


def stock_quantities(db: Session, product_id: int) -> dict[int | None, int]:
    """Return on-hand quantities separately for the base product and each variant."""
    rows = db.execute(
        select(
            StockLevel.variant_id,
            func.coalesce(func.sum(StockLevel.quantity), 0),
        )
        .where(StockLevel.product_id == product_id)
        .group_by(StockLevel.variant_id)
    )
    quantities = {variant_id: int(quantity) for variant_id, quantity in rows}

    serial_rows = db.execute(
        select(SerialNumber.variant_id, func.count())
        .where(
            SerialNumber.product_id == product_id,
            SerialNumber.status == "in_stock",
        )
        .group_by(SerialNumber.variant_id)
    )
    for variant_id, quantity in serial_rows:
        quantities[variant_id] = quantities.get(variant_id, 0) + int(quantity)

    return quantities


def location_exists(db: Session, location_id: int) -> bool:
    """Validate a location without exposing the stock table to auth."""
    return (
        db.scalar(
            select(Location.id).where(
                Location.id == location_id,
                Location.is_active,
            )
        )
        is not None
    )
