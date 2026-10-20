"""Public service interface of the `product` module."""

from typing import Protocol


class ProductService(Protocol):
    """Operations the `product` module offers to other modules.

    Methods are added as features land; callers depend on this interface,
    never on `_internal`.
    """
