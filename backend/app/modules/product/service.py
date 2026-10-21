"""Public service interface of the `product` module."""

from typing import Protocol

from sqlalchemy.orm import Session


class ProductService(Protocol):
    """Operations the `product` module offers to other modules.

    Methods are added as features land; callers depend on this interface,
    never on `_internal`.
    """


class StockCheck(Protocol):
    def __call__(self, db: Session, product_id: int) -> bool: ...
