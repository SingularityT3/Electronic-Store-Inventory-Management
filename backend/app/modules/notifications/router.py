"""HTTP routes for the `notifications` module."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.modules.auth import CurrentUser, Permission, authorize_location, require
from app.modules.notifications import StockAlertData, active_stock_alerts
from app.modules.notifications._internal.models import Notification

router = APIRouter(prefix="/notifications", tags=["notifications"])


class StockAlertOut(BaseModel):
    id: int
    product_id: int
    variant_id: int | None
    product_name: str
    sku: str
    variant_sku: str | None
    location_id: int
    location_name: str
    alert_type: str
    quantity: int
    threshold: int


class NotificationOut(BaseModel):
    id: int
    type: str
    title: str
    message: str
    is_read: bool
    created_at: datetime


@router.get("", response_model=list[NotificationOut])
def list_notifications(
    db: Annotated[Session, Depends(get_session)],
    user: Annotated[CurrentUser, Depends(require(Permission.NOTIFICATIONS_VIEW))],
) -> list[NotificationOut]:
    notifications = db.scalars(
        select(Notification)
        .where(Notification.recipient_user_id == user.id)
        .order_by(Notification.created_at, Notification.id)
    ).all()
    return [
        NotificationOut.model_validate(notification, from_attributes=True)
        for notification in notifications
    ]


@router.get(
    "/alerts",
    response_model=list[StockAlertOut],
)
def list_stock_alerts(
    db: Annotated[Session, Depends(get_session)],
    user: Annotated[CurrentUser, Depends(require(Permission.NOTIFICATIONS_VIEW))],
    location_id: Annotated[int | None, Query(ge=1)] = None,
) -> list[StockAlertOut]:
    if not user.sees_all_locations:
        if location_id is not None:
            authorize_location(db, user, location_id, "View stock alerts")
        location_id = user.location_id

    alerts: list[StockAlertData] = active_stock_alerts(db, location_id=location_id)
    return [StockAlertOut.model_validate(alert, from_attributes=True) for alert in alerts]
