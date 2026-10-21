"""HTTP routes for the `stock` module."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.modules.auth import Permission, require
from app.modules.stock._internal.models import Location

router = APIRouter(prefix="/stock", tags=["stock"])


class LocationOut(BaseModel):
    id: int
    name: str
    type: str


@router.get("/locations", dependencies=[Depends(require(Permission.STOCK_VIEW))])
def list_locations(db: Annotated[Session, Depends(get_session)]) -> list[LocationOut]:
    locations = db.scalars(select(Location).where(Location.is_active).order_by(Location.name)).all()
    return [LocationOut.model_validate(location, from_attributes=True) for location in locations]
