"""Public service interface of the `purchasing` module."""

from typing import Protocol


class PurchasingService(Protocol):
    """Operations the `purchasing` module offers to other modules.

    Methods are added as features land; callers depend on this interface,
    never on `_internal`.
    """
