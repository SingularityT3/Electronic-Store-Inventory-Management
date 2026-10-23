"""Public service interface of the `stock` module."""

from collections.abc import Sequence
from typing import Protocol

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.modules.stock._internal.models import Location, SerialNumber, StockLevel


class StockService(Protocol):
    """Operations the `stock` module offers to other modules.

    Methods are added as features land; callers depend on this interface,
    never on `_internal`.
    """


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


def stock_quantities(
    db: Session,
    product_ids: int | Sequence[int],
    location_id: int | None = None,
    all_locations: bool = True,
) -> dict[int, dict[int | None, int]]:
    """Return batched on-hand quantities, optionally scoped to one location."""
    ids = [product_ids] if isinstance(product_ids, int) else list(product_ids)
    if not ids:
        return {}
    stock_filter = [StockLevel.product_id.in_(ids)]
    serial_filter = [
        SerialNumber.product_id.in_(ids),
        SerialNumber.status == "in_stock",
    ]
    if not all_locations:
        stock_filter.append(StockLevel.location_id == location_id)
        serial_filter.append(SerialNumber.location_id == location_id)
    rows = db.execute(
        select(StockLevel.variant_id, func.coalesce(func.sum(StockLevel.quantity), 0))
        .add_columns(StockLevel.product_id)
        .where(*stock_filter)
        .group_by(StockLevel.product_id, StockLevel.variant_id)
    )
    quantities: dict[int, dict[int | None, int]] = {}
    for variant_id, quantity, product_id in rows:
        quantities.setdefault(product_id, {})[variant_id] = int(quantity)
    serial_rows = db.execute(
        select(SerialNumber.variant_id, func.count())
        .add_columns(SerialNumber.product_id)
        .where(*serial_filter)
        .group_by(SerialNumber.product_id, SerialNumber.variant_id)
    )
    for variant_id, quantity, product_id in serial_rows:
        product_quantities = quantities.setdefault(product_id, {})
        product_quantities[variant_id] = product_quantities.get(variant_id, 0) + int(quantity)
    return quantities


def location_exists(db: Session, location_id: int) -> bool:
    """Validate a location without exposing the stock table to auth."""
    return (
        db.scalar(select(Location.id).where(Location.id == location_id, Location.is_active))
        is not None
    )
