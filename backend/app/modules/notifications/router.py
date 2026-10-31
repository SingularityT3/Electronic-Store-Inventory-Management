"""HTTP routes for the `notifications` module."""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.modules.auth import CurrentUser, Permission, authorize_location, require
from app.modules.notifications import (
    NotificationData,
    StockAlertData,
    active_stock_alerts,
    dismiss,
    list_user_notifications,
    mark_all_read,
    mark_read,
    unread_count,
)
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
    location_id: int | None = None
    location_name: str | None = None
    reference_type: str | None = None
    reference_id: int | None = None
    links: dict[str, Any] | None = None


class UnreadCountOut(BaseModel):
    unread: int


@router.get("", response_model=list[NotificationOut])
def list_notifications(
    db: Annotated[Session, Depends(get_session)],
    user: Annotated[CurrentUser, Depends(require(Permission.NOTIFICATIONS_VIEW))],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    unread_only: bool = False,
    include_read: bool = True,
) -> list[NotificationOut]:
    notifications_data = list_user_notifications(
        db,
        user_id=user.id,
        limit=limit,
        offset=offset,
        unread_only=unread_only,
        include_read=include_read,
    )

    # Enhance with location_name and links
    result = []
    for nd in notifications_data:
        # Get location name if available
        location_name = nd.location_name
        if nd.location_id and location_name is None:
            location_name = db.scalar(
                select(Notification.location_id)
                .where(Notification.id == nd.id)
            )
            # Note: We'd need a join or separate query, but for simplicity
            # we'll add the location name if we can get it from stock_alerts
            if nd.reference_type == "stock_alert" and nd.reference_id:
                from app.modules.notifications._internal.models import StockAlert
                alert = db.get(StockAlert, nd.reference_id)
                if alert:
                    location_name = alert.location_name

        links = None
        if nd.reference_type == "stock_alert" and nd.reference_id:
            from app.modules.notifications._internal.models import StockAlert
            alert = db.get(StockAlert, nd.reference_id)
            if alert:
                links = {
                    "product_id": alert.product_id,
                    "variant_id": alert.variant_id,
                    "location_id": alert.location_id,
                }
        elif nd.reference_type == "purchase_order" and nd.reference_id:
            links = {"purchase_order_id": nd.reference_id}

        result.append(
            NotificationOut(
                id=nd.id,
                type=nd.type,
                title=nd.title,
                message=nd.message,
                is_read=nd.is_read,
                created_at=nd.created_at,
                location_id=nd.location_id,
                location_name=location_name,
                reference_type=nd.reference_type,
                reference_id=nd.reference_id,
                links=links,
            )
        )

    return result


@router.get(
    "/unread-count",
    response_model=UnreadCountOut,
)
def get_unread_count(
    db: Annotated[Session, Depends(get_session)],
    user: Annotated[CurrentUser, Depends(require(Permission.NOTIFICATIONS_VIEW))],
) -> UnreadCountOut:
    return UnreadCountOut(unread=unread_count(db, user_id=user.id))


@router.post(
    "/{notification_id}/read",
    status_code=status.HTTP_200_OK,
)
def read_notification(
    notification_id: int,
    db: Annotated[Session, Depends(get_session)],
    user: Annotated[CurrentUser, Depends(require(Permission.NOTIFICATIONS_VIEW))],
) -> dict[str, str]:
    try:
        mark_read(db, user_id=user.id, notification_id=notification_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    return {"status": "read"}


@router.post(
    "/read-all",
    status_code=status.HTTP_200_OK,
)
def read_all_notifications(
    db: Annotated[Session, Depends(get_session)],
    user: Annotated[CurrentUser, Depends(require(Permission.NOTIFICATIONS_VIEW))],
) -> dict[str, str]:
    mark_all_read(db, user_id=user.id)
    return {"status": "all_read"}


@router.post(
    "/{notification_id}/dismiss",
    status_code=status.HTTP_200_OK,
)
def dismiss_notification(
    notification_id: int,
    db: Annotated[Session, Depends(get_session)],
    user: Annotated[CurrentUser, Depends(require(Permission.NOTIFICATIONS_VIEW))],
) -> dict[str, str]:
    try:
        dismiss(db, user_id=user.id, notification_id=notification_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    return {"status": "dismissed"}


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