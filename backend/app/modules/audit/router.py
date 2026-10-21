"""HTTP routes for the `audit` module: the Admin-only audit log viewer (UC-03).

`app/main.py` mounts this router behind `require(Permission.AUDIT_VIEW)`, since `audit` sits
below `auth` and cannot import it. The routes only read: there is no route that edits or
deletes an entry, for any role (NFR-8, SEC-AUD-2).
"""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import AwareDatetime, BaseModel
from sqlalchemy.orm import Session

from app.db import get_session
from app.modules.audit import AuditFilter, audit_service

router = APIRouter(prefix="/audit", tags=["audit"])

DbSession = Annotated[Session, Depends(get_session)]


class AuditEntryOut(BaseModel):
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


class AuditPageOut(BaseModel):
    entries: list[AuditEntryOut]
    total: int
    limit: int
    offset: int


class AuditFilterOptionsOut(BaseModel):
    usernames: list[str]
    actions: list[str]
    modules: list[str]


@router.get("/entries")
def list_entries(
    db: DbSession,
    username: Annotated[str | None, Query(max_length=150)] = None,
    action: Annotated[str | None, Query(max_length=100)] = None,
    module: Annotated[str | None, Query(max_length=50)] = None,
    since: Annotated[AwareDatetime | None, Query(description="Inclusive, with offset")] = None,
    until: Annotated[AwareDatetime | None, Query(description="Exclusive, with offset")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditPageOut:
    """Entries matching every given filter, newest first."""
    if since is not None and until is not None and since >= until:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "since must be before until")
    where = AuditFilter(username=username, action=action, module=module, since=since, until=until)
    page = audit_service.list_entries(db, where, limit=limit, offset=offset)
    return AuditPageOut(
        entries=[AuditEntryOut.model_validate(e, from_attributes=True) for e in page.entries],
        total=page.total,
        limit=limit,
        offset=offset,
    )


@router.get("/filters")
def filter_options(db: DbSession) -> AuditFilterOptionsOut:
    """The usernames, actions and modules present in the log."""
    return AuditFilterOptionsOut.model_validate(
        audit_service.filter_options(db), from_attributes=True
    )
