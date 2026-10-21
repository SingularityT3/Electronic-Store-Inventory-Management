"""Public service interface of the `audit` module."""

from typing import Any, Protocol

from sqlalchemy.orm import Session


class AuditService(Protocol):
    """Operations the `audit` module offers to other modules.

    Methods are added as features land; callers depend on this interface,
    never on `_internal`.
    """

    def record(
        self,
        db: Session,
        *,
        module: str,
        action: str,
        user_id: int | None = None,
        username: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        details: str | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> None:
        """Add an entry to the audit log in the caller's transaction.

        The entry is written when the caller commits, so it is kept or rolled back
        together with the change it describes. Never pass passwords or tokens.
        """
        ...
