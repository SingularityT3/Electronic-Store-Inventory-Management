"""Implementation of `AuditService`."""

from collections.abc import Mapping
from datetime import date, datetime, time
from enum import Enum
from typing import Any

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from app.modules.audit._internal.models import AuditLog
from app.modules.audit.service import AuditEntry, AuditFilter, AuditFilterOptions, AuditPage


def json_value(value: Any) -> Any:
    """`value` as something JSONB can store. Decimals become strings, so no cents are lost."""
    if isinstance(value, Mapping):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [json_value(v) for v in value]
    if isinstance(value, Enum):
        return json_value(value.value)
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    if value is None or isinstance(value, bool | int | float | str):
        return value
    return str(value)  # Decimal, UUID, ...


def changes(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The fields that differ between two snapshots of a record, as (old, new).

    A field missing from one side counts as None there. Pass the result as `before` and
    `after` to `record`, e.g. a price edit gives ({"price": "28999.00"}, {"price": "26999.00"}).
    """
    old = json_value(before)
    new = json_value(after)
    changed = [k for k in {**old, **new} if old.get(k) != new.get(k)]
    return {k: old.get(k) for k in changed}, {k: new.get(k) for k in changed}


def _conditions(where: AuditFilter) -> list[ColumnElement[bool]]:
    conditions = []
    if where.username:
        conditions.append(func.lower(AuditLog.username) == where.username.lower())
    if where.action:
        conditions.append(AuditLog.action == where.action)
    if where.module:
        conditions.append(AuditLog.module == where.module)
    if where.since is not None:
        conditions.append(AuditLog.occurred_at >= where.since)
    if where.until is not None:
        conditions.append(AuditLog.occurred_at < where.until)
    return conditions


def _entry(row: AuditLog) -> AuditEntry:
    return AuditEntry(
        id=row.id,
        occurred_at=row.occurred_at,
        user_id=row.user_id,
        username=row.username,
        module=row.module,
        action=row.action,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        details=row.details,
        before=row.before,
        after=row.after,
    )


class DbAuditService:
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
        db.add(
            AuditLog(
                module=module,
                action=action,
                user_id=user_id,
                username=username,
                entity_type=entity_type,
                entity_id=entity_id,
                details=details,
                before=None if before is None else json_value(before),
                after=None if after is None else json_value(after),
            )
        )

    def list_entries(
        self, db: Session, where: AuditFilter, *, limit: int, offset: int
    ) -> AuditPage:
        conditions = _conditions(where)
        total = db.scalar(select(func.count()).select_from(AuditLog).where(*conditions))
        rows = db.scalars(
            select(AuditLog)
            .where(*conditions)
            # Entries of one transaction share occurred_at; id keeps their order.
            .order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return AuditPage(entries=[_entry(row) for row in rows], total=total or 0)

    def filter_options(self, db: Session) -> AuditFilterOptions:
        def distinct(column: Any) -> list[str]:
            return list(
                db.scalars(select(column).where(column.is_not(None)).distinct().order_by(column))
            )

        return AuditFilterOptions(
            usernames=distinct(AuditLog.username),
            actions=distinct(AuditLog.action),
            modules=distinct(AuditLog.module),
        )
