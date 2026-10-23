"""HTTP routes for the `sales` module."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_session
from app.modules.auth import CurrentUser, Permission, authorize_location, require
from app.modules.stock import location_exists, stock_positions

router = APIRouter(prefix="/sales", tags=["sales"])


class AvailabilityOut(BaseModel):
    product_id: int
    product_name: str
    sku: str
    variant_id: int | None
    variant_sku: str | None
    variant_attributes: dict[str, object] | None
    location_id: int
    location_name: str
    available_quantity: int


@router.get("/availability", response_model=list[AvailabilityOut])
def item_availability(
    db: Annotated[Session, Depends(get_session)],
    user: Annotated[CurrentUser, Depends(require(Permission.SALES_RECORD))],
    location_id: Annotated[int | None, Query(ge=1)] = None,
) -> list[AvailabilityOut]:
    """Stock available to sell at one location; cashiers are always scoped to their own."""
    if not user.sees_all_locations:
        if location_id is not None:
            authorize_location(db, user, location_id, "View POS availability")
        location_id = user.location_id
    elif location_id is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Choose a location to view POS availability.",
        )

    if location_id is None or not location_exists(db, location_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found.")

    return [
        AvailabilityOut(
            product_id=position.product_id,
            product_name=position.product_name,
            sku=position.sku,
            variant_id=position.variant_id,
            variant_sku=position.variant_sku,
            variant_attributes=position.variant_attributes,
            location_id=position.location_id,
            location_name=position.location_name,
            available_quantity=position.quantity,
        )
        for position in stock_positions(db, location_id=location_id)
    ]
