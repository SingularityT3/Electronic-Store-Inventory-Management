"""Public service interface of the `auth` module."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CurrentUser:
    """The signed-in user of a request, as given by the `current_user` dependency."""

    id: int
    username: str
    full_name: str
    role: str
    location_id: int | None


class AuthService(Protocol):
    """Operations the `auth` module offers to other modules.

    Methods are added as features land; callers depend on this interface,
    never on `_internal`. Routes get the signed-in user from the `current_user`
    dependency exported by this module.
    """
