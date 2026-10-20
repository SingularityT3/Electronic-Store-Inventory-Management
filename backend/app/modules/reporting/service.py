"""Public service interface of the `reporting` module."""

from typing import Protocol


class ReportingService(Protocol):
    """Operations the `reporting` module offers to other modules.

    Methods are added as features land; callers depend on this interface,
    never on `_internal`.
    """
