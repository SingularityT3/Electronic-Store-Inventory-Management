"""Public service interface of the `notifications` module."""

from typing import Protocol


class NotificationsService(Protocol):
    """Operations the `notifications` module offers to other modules.

    Methods are added as features land; callers depend on this interface,
    never on `_internal`.
    """
