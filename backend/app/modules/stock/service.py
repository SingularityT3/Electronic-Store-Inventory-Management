"""Public service interface of the `stock` module."""

from typing import Protocol

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.modules.stock._internal.models import SerialNumber, StockLevel


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
