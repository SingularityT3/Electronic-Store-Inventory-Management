"""HTTP routes for the `stock` module."""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_session
from app.modules.auth import CurrentUser, Permission, authorize_location, require
from app.modules.product import product_stock_items
from app.modules.stock import reevaluate_stock_alert, stock_positions, transfer_stock
from app.modules.stock._internal.models import Location, StockLevel
from app.modules.stock.service import StockTransferError, StockTransferResult

router = APIRouter(prefix="/stock", tags=["stock"])


class LocationOut(BaseModel):
    id: int
    name: str
    type: str


class ManagedLocationOut(LocationOut):
    address: str | None
    is_active: bool


class StockLevelOut(BaseModel):
    product_id: int
    product_name: str
    sku: str
    category_id: int
    category_name: str
    variant_id: int | None
    variant_sku: str | None
    variant_attributes: dict[str, object] | None
    location_id: int
    location_name: str
    quantity: int
    total_quantity: int
    reorder_threshold: int
    reorder_to_level: int


class ReorderSettingsUpdate(BaseModel):
    product_id: int = Field(ge=1)
    variant_id: int | None = Field(default=None, ge=1)
    location_id: int = Field(ge=1)
    reorder_threshold: int = Field(ge=0)
    reorder_to_level: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def reorder_to_level_is_valid(self) -> "ReorderSettingsUpdate":
        if self.reorder_to_level is not None and self.reorder_to_level < self.reorder_threshold:
            raise ValueError("Reorder-to level cannot be below the reorder threshold.")
        return self


class ReorderSettingsOut(BaseModel):
    product_id: int
    variant_id: int | None
    location_id: int
    reorder_threshold: int
    reorder_to_level: int | None


class StockTransferCreate(BaseModel):
    product_id: int = Field(gt=0)
    variant_id: int | None = Field(default=None, gt=0)
    from_location_id: int = Field(gt=0)
    to_location_id: int = Field(gt=0)
    quantity: int = Field(gt=0)

    @model_validator(mode="after")
    def locations_must_differ(self) -> "StockTransferCreate":
        if self.from_location_id == self.to_location_id:
            raise ValueError("Source and destination locations must be different.")
        return self


class StockTransferOut(BaseModel):
    id: int
    product_id: int
    variant_id: int | None
    from_location_id: int
    to_location_id: int
    quantity: int
    created_at: datetime


class LocationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: Literal["store", "warehouse"]
    address: str | None = None
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Location name cannot be blank.")
        return value


class LocationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    type: Literal["store", "warehouse"] | None = None
    address: str | None = None
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Location name cannot be blank.")
        return value


def _commit_location(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint_name != "uq_locations_name":
            raise
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A location with this name already exists."
        ) from None


@router.get("/locations")
def list_locations(
    db: Annotated[Session, Depends(get_session)],
    user: Annotated[CurrentUser, Depends(require(Permission.STOCK_VIEW))],
) -> list[LocationOut]:
    query = select(Location).where(Location.is_active)
    if not user.sees_all_locations:
        query = query.where(Location.id == user.location_id)
    locations = db.scalars(query.order_by(Location.name)).all()
    return [LocationOut.model_validate(location, from_attributes=True) for location in locations]


@router.get("/levels")
def list_stock_levels(
    db: Annotated[Session, Depends(get_session)],
    user: Annotated[CurrentUser, Depends(require(Permission.STOCK_VIEW))],
    location_id: Annotated[int | None, Query(ge=1)] = None,
) -> list[StockLevelOut]:
    if not user.sees_all_locations:
        if location_id is not None:
            authorize_location(db, user, location_id, "View stock levels")
        location_id = user.location_id

    if location_id is not None:
        location = db.scalar(select(Location).where(Location.id == location_id, Location.is_active))
        if location is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found.")

    positions = stock_positions(db)
    if not user.sees_all_locations:
        positions = [position for position in positions if position.location_id == user.location_id]
    totals: dict[tuple[int, int | None], int] = {}
    for position in positions:
        key = (position.product_id, position.variant_id)
        totals[key] = totals.get(key, 0) + position.quantity

    return [
        StockLevelOut(
            product_id=position.product_id,
            product_name=position.product_name,
            sku=position.sku,
            category_id=position.category_id,
            category_name=position.category_name,
            variant_id=position.variant_id,
            variant_sku=position.variant_sku,
            variant_attributes=position.variant_attributes,
            location_id=position.location_id,
            location_name=position.location_name,
            quantity=position.quantity,
            total_quantity=totals[(position.product_id, position.variant_id)],
            reorder_threshold=position.reorder_threshold,
            reorder_to_level=position.reorder_to_level,
        )
        for position in positions
        if location_id is None or position.location_id == location_id
    ]


@router.patch(
    "/levels/reorder-settings",
    response_model=ReorderSettingsOut,
)
def update_reorder_settings(
    body: ReorderSettingsUpdate,
    db: Annotated[Session, Depends(get_session)],
    user: Annotated[CurrentUser, Depends(require(Permission.STOCK_ADJUST))],
) -> ReorderSettingsOut:
    authorize_location(db, user, body.location_id, "Update stock reorder settings")
    location = db.scalar(
        select(Location).where(Location.id == body.location_id, Location.is_active)
    )
    if location is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found.")

    item_exists = any(
        item.product_id == body.product_id and item.variant_id == body.variant_id
        for item in product_stock_items(db)
    )
    if not item_exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Stock item not found.")

    statement = (
        insert(StockLevel)
        .values(
            product_id=body.product_id,
            variant_id=body.variant_id,
            location_id=body.location_id,
            quantity=0,
            reorder_threshold=body.reorder_threshold,
            reorder_to_level=body.reorder_to_level,
        )
        .on_conflict_do_update(
            index_elements=[
                StockLevel.product_id,
                StockLevel.variant_id,
                StockLevel.location_id,
            ],
            set_={
                "reorder_threshold": body.reorder_threshold,
                "updated_at": func.now(),
                **(
                    {"reorder_to_level": body.reorder_to_level}
                    if "reorder_to_level" in body.model_fields_set
                    else {}
                ),
            },
        )
    )
    db.execute(statement)
    db.flush()
    reevaluate_stock_alert(
        db,
        product_id=body.product_id,
        variant_id=body.variant_id,
        location_id=body.location_id,
    )
    level = db.scalar(
        select(StockLevel).where(
            StockLevel.product_id == body.product_id,
            StockLevel.variant_id.is_not_distinct_from(body.variant_id),
            StockLevel.location_id == body.location_id,
        )
    )
    if level is None:
        raise RuntimeError("Stock level was not available after updating reorder settings.")
    db.commit()
    db.refresh(level)
    return ReorderSettingsOut(
        product_id=level.product_id,
        variant_id=level.variant_id,
        location_id=level.location_id,
        reorder_threshold=level.reorder_threshold,
        reorder_to_level=level.reorder_to_level,
    )


@router.post(
    "/locations",
    response_model=ManagedLocationOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require(Permission.LOCATIONS_MANAGE))],
)
def create_location(
    body: LocationCreate, db: Annotated[Session, Depends(get_session)]
) -> ManagedLocationOut:
    location = Location(**body.model_dump())
    db.add(location)
    _commit_location(db)
    db.refresh(location)
    return ManagedLocationOut.model_validate(location, from_attributes=True)


@router.patch(
    "/locations/{location_id}",
    response_model=ManagedLocationOut,
    dependencies=[Depends(require(Permission.LOCATIONS_MANAGE))],
)
def update_location(
    location_id: int,
    body: LocationUpdate,
    db: Annotated[Session, Depends(get_session)],
) -> ManagedLocationOut:
    location = db.get(Location, location_id)
    if location is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found.")

    values = body.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Provide at least one field.")
    for field in ("name", "type", "is_active"):
        if field in values and values[field] is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Location {field} cannot be null.",
            )

    for field, value in values.items():
        setattr(location, field, value)
    _commit_location(db)
    db.refresh(location)
    return ManagedLocationOut.model_validate(location, from_attributes=True)


@router.post(
    "/transfers",
    response_model=StockTransferOut,
    status_code=status.HTTP_201_CREATED,
)
def create_stock_transfer(
    body: StockTransferCreate,
    db: Annotated[Session, Depends(get_session)],
    user: Annotated[CurrentUser, Depends(require(Permission.STOCK_TRANSFER))],
) -> StockTransferOut:
    authorize_location(db, user, body.from_location_id, "Transfer stock")
    try:
        transfer: StockTransferResult = transfer_stock(
            db,
            product_id=body.product_id,
            variant_id=body.variant_id,
            from_location_id=body.from_location_id,
            to_location_id=body.to_location_id,
            quantity=body.quantity,
            user_id=user.id,
            username=user.username,
        )
        db.commit()
    except StockTransferError as exc:
        db.rollback()
        raise HTTPException(exc.status_code, exc.detail) from exc
    except Exception:
        db.rollback()
        raise

    return StockTransferOut(
        id=transfer.id,
        product_id=transfer.product_id,
        variant_id=transfer.variant_id,
        from_location_id=transfer.from_location_id,
        to_location_id=transfer.to_location_id,
        quantity=transfer.quantity,
        created_at=transfer.created_at,
    )


@router.get(
    "/transfers/locations",
    response_model=list[LocationOut],
    dependencies=[Depends(require(Permission.STOCK_TRANSFER))],
)
def list_transfer_locations(db: Annotated[Session, Depends(get_session)]) -> list[LocationOut]:
    locations = db.scalars(select(Location).where(Location.is_active).order_by(Location.name)).all()
    return [LocationOut.model_validate(location, from_attributes=True) for location in locations]
