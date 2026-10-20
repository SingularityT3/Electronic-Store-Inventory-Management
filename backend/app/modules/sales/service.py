"""Public service interface of the `sales` module."""

from typing import Protocol


class SalesService(Protocol):
    """Operations the `sales` module offers to other modules.

    Methods are added as features land; callers depend on this interface,
    never on `_internal`.
    """
