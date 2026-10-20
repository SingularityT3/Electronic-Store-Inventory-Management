"""FastAPI dependencies for authenticated routes (FR-5.2, SEC-AUTH-1, SEC-SES-1)."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_session
from app.modules.auth._internal.sessions import SESSION_COOKIE, resolve_session
from app.modules.auth.service import CurrentUser


def utcnow() -> datetime:
    return datetime.now(UTC)


def current_user(
    request: Request,
    db: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CurrentUser:
    """The signed-in user. Responds 401 if there is no valid session."""
    token = request.cookies.get(SESSION_COOKIE)
    user = resolve_session(db, token, settings, utcnow()) if token else None
    db.commit()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in or session expired")
    return CurrentUser(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        location_id=user.location_id,
    )
