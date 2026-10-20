"""Public service interface of the `stock` module."""

from typing import Protocol


class StockService(Protocol):
    """Operations the `stock` module offers to other modules.

    Methods are added as features land; callers depend on this interface,
    never on `_internal`.
    """
