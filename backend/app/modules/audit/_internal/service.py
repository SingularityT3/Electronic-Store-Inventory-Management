"""Implementation of `AuditService`."""

from typing import Any

from sqlalchemy.orm import Session

from app.modules.audit._internal.models import AuditLog


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
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
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
                before=before,
                after=after,
            )
        )
