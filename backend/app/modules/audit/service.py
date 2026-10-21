"""Public service interface of the `audit` module."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy.orm import Session


@dataclass(frozen=True)
class AuditEntry:
    """One audit log entry. Every module's entries have these same fields (FR5.3-IT-1)."""

    id: int
    occurred_at: datetime
    user_id: int | None
    username: str | None
    module: str
    action: str
    entity_type: str | None
    entity_id: str | None
    details: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None


@dataclass(frozen=True)
class AuditFilter:
    """Which entries to list (UC-03, SEC-AUD-4). Unset fields match everything."""

    username: str | None = None
    """Exact username, any case."""
    action: str | None = None
    module: str | None = None
    since: datetime | None = None
    """Inclusive."""
    until: datetime | None = None
    """Exclusive."""


@dataclass(frozen=True)
class AuditPage:
    entries: list[AuditEntry]
    total: int
    """Matching entries across all pages."""


@dataclass(frozen=True)
class AuditFilterOptions:
    """Values present in the log, for the viewer's filter lists."""

    usernames: list[str]
    actions: list[str]
    modules: list[str]


class AuditService(Protocol):
    """Operations the `audit` module offers to other modules.

    Methods are added as features land; callers depend on this interface,
    never on `_internal`. The log is append-only: there is deliberately no way to
    change or remove an entry (NFR-8, SEC-AUD-2), and the database rejects it too.
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
        before: Mapping[str, Any] | None = None,
        after: Mapping[str, Any] | None = None,
    ) -> None:
        """Add an entry to the audit log in the caller's transaction.

        The entry is written when the caller commits, so it is kept or rolled back
        together with the change it describes. Never pass passwords or tokens.
        `before` and `after` may hold Decimals, dates and enums; they are stored as JSON
        strings. For an edit, `changes(old, new)` gives just the fields that changed.
        """
        ...

    def list_entries(
        self, db: Session, where: AuditFilter, *, limit: int, offset: int
    ) -> AuditPage:
        """Matching entries, newest first."""
        ...

    def filter_options(self, db: Session) -> AuditFilterOptions: ...
