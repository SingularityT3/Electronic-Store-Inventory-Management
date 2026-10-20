"""Public service interface of the `auth` module."""

from typing import Protocol


class AuthService(Protocol):
    """Operations the `auth` module offers to other modules.

    Methods are added as features land; callers depend on this interface,
    never on `_internal`.
    """
