"""Health check used by container health checks and the uptime monitor (NFR-4)."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
def health(
    response: Response, session: Annotated[Session, Depends(get_session)]
) -> dict[str, object]:
    """200 when the app and the database answer, 503 otherwise."""
    try:
        session.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        logger.exception("Health check: database is unreachable")
        database = "error"
    healthy = database == "ok"
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if healthy else "unhealthy", "checks": {"database": database}}
