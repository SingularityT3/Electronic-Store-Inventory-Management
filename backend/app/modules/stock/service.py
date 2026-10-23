"""Public service interface of the `stock` module."""

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


def stock_quantities(db: Session, product_id: int) -> dict[int | None, int]:
    """Return on-hand quantities separately for the base product and each variant."""
    rows = db.execute(
        select(StockLevel.variant_id, func.coalesce(func.sum(StockLevel.quantity), 0))
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
        db.scalar(select(Location.id).where(Location.id == location_id, Location.is_active))
        is not None
    )
