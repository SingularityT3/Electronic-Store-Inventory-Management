"""Public service interface of the `audit` module."""

from typing import Protocol


class AuditService(Protocol):
    """Operations the `audit` module offers to other modules.

    Methods are added as features land; callers depend on this interface,
    never on `_internal`.
    """
