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
from app.modules.audit import audit_service, changes
from app.modules.auth import CurrentUser, Permission, authorize_location, require
from app.modules.product import product_stock_item
from app.modules.stock import (
    adjust_stock,
    reevaluate_stock_alert,
    stock_positions,
    transfer_stock,
)
from app.modules.stock._internal.models import Location, StockLevel
from app.modules.stock.service import (
    ReasonCode,
    StockAdjustmentError,
    StockTransferError,
    StockTransferResult,
)

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


class StockAdjustmentCreate(BaseModel):
    product_id: int = Field(gt=0)
    variant_id: int | None = Field(default=None, gt=0)
    location_id: int = Field(gt=0)
    quantity_change: int
    reason: str = ""
    reason_code: ReasonCode = "correction"


class StockAdjustmentOut(BaseModel):
    product_id: int
    variant_id: int | None
    location_id: int
    quantity_change: int
    previous_quantity: int
    quantity: int


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


def _commit_location(db: Session, *, flush_only: bool = False) -> None:
    try:
        if flush_only:
            db.flush()
        else:
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

    item = product_stock_item(db, body.product_id, body.variant_id)
    if item is None or not item.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Stock item not found.")

    if "reorder_to_level" not in body.model_fields_set:
        current_to_level = db.scalar(
            select(StockLevel.reorder_to_level).where(
                StockLevel.product_id == body.product_id,
                StockLevel.variant_id.is_not_distinct_from(body.variant_id),
                StockLevel.location_id == body.location_id,
            )
        )
        if current_to_level is not None and current_to_level < body.reorder_threshold:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Reorder-to level cannot be below the reorder threshold.",
            )

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
    previous = db.execute(
        select(StockLevel.reorder_threshold, StockLevel.reorder_to_level).where(
            StockLevel.product_id == body.product_id,
            StockLevel.variant_id.is_not_distinct_from(body.variant_id),
            StockLevel.location_id == body.location_id,
        )
    ).one_or_none()
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
    db.refresh(level)
    old, new = changes(
        {
            "reorder_threshold": previous.reorder_threshold if previous else None,
            "reorder_to_level": previous.reorder_to_level if previous else None,
        },
        {"reorder_threshold": level.reorder_threshold, "reorder_to_level": level.reorder_to_level},
    )
    if old:
        audit_service.record(
            db,
            module="stock",
            action="reorder_settings_updated",
            user_id=user.id,
            username=user.username,
            entity_type="stock_level",
            entity_id=f"{body.product_id}:{body.variant_id}:{body.location_id}",
            before=old,
            after=new,
        )
    db.commit()
    db.refresh(level)
    return ReorderSettingsOut(
        product_id=level.product_id,
        variant_id=level.variant_id,
        location_id=level.location_id,
        reorder_threshold=level.reorder_threshold,
        reorder_to_level=level.reorder_to_level,
    )


def _location_snapshot(location: Location) -> dict[str, object]:
    return {
        "name": location.name,
        "type": location.type,
        "address": location.address,
        "is_active": location.is_active,
    }


def _audit_location(
    db: Session,
    user: CurrentUser,
    action: str,
    location: Location,
    before: dict[str, object] | None,
    after: dict[str, object],
) -> None:
    audit_service.record(
        db,
        module="stock",
        action=action,
        user_id=user.id,
        username=user.username,
        entity_type="location",
        entity_id=str(location.id),
        before=before,
        after=after,
    )


@router.get("/locations/all", response_model=list[ManagedLocationOut])
def list_all_locations(
    db: Annotated[Session, Depends(get_session)],
    _user: Annotated[CurrentUser, Depends(require(Permission.LOCATIONS_MANAGE))],
) -> list[ManagedLocationOut]:
    """Every location, inactive ones included, for the location management screen."""
    locations = db.scalars(select(Location).order_by(Location.name)).all()
    return [ManagedLocationOut.model_validate(item, from_attributes=True) for item in locations]


@router.post(
    "/locations",
    response_model=ManagedLocationOut,
    status_code=status.HTTP_201_CREATED,
)
def create_location(
    body: LocationCreate,
    db: Annotated[Session, Depends(get_session)],
    user: Annotated[CurrentUser, Depends(require(Permission.LOCATIONS_MANAGE))],
) -> ManagedLocationOut:
    location = Location(**body.model_dump())
    db.add(location)
    _commit_location(db, flush_only=True)
    _audit_location(db, user, "location_created", location, None, _location_snapshot(location))
    _commit_location(db)
    db.refresh(location)
    return ManagedLocationOut.model_validate(location, from_attributes=True)


@router.patch(
    "/locations/{location_id}",
    response_model=ManagedLocationOut,
)
def update_location(
    location_id: int,
    body: LocationUpdate,
    db: Annotated[Session, Depends(get_session)],
    user: Annotated[CurrentUser, Depends(require(Permission.LOCATIONS_MANAGE))],
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

    before = _location_snapshot(location)
    for field, value in values.items():
        setattr(location, field, value)
    old, new = changes(before, _location_snapshot(location))
    if old:
        _audit_location(db, user, "location_updated", location, old, new)
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


@router.post(
    "/adjustments",
    response_model=StockAdjustmentOut,
    status_code=status.HTTP_201_CREATED,
)
def create_stock_adjustment(
    body: StockAdjustmentCreate,
    db: Annotated[Session, Depends(get_session)],
    user: Annotated[CurrentUser, Depends(require(Permission.STOCK_ADJUST))],
) -> StockAdjustmentOut:
    authorize_location(db, user, body.location_id, "Adjust stock")
    try:
        result = adjust_stock(
            db,
            product_id=body.product_id,
            variant_id=body.variant_id,
            location_id=body.location_id,
            quantity_change=body.quantity_change,
            reason=body.reason,
            reason_code=body.reason_code,
            user_id=user.id,
            username=user.username,
        )
        db.commit()
    except StockAdjustmentError as exc:
        db.rollback()
        raise HTTPException(exc.status_code, exc.detail) from exc
    except Exception:
        db.rollback()
        raise
    return StockAdjustmentOut(
        product_id=result.product_id,
        variant_id=result.variant_id,
        location_id=result.location_id,
        quantity_change=result.quantity_delta,
        previous_quantity=result.previous_quantity,
        quantity=result.quantity,
    )


@router.get(
    "/transfers/locations",
    response_model=list[LocationOut],
    dependencies=[Depends(require(Permission.STOCK_TRANSFER))],
)
def list_transfer_locations(db: Annotated[Session, Depends(get_session)]) -> list[LocationOut]:
    locations = db.scalars(select(Location).where(Location.is_active).order_by(Location.name)).all()
    return [LocationOut.model_validate(location, from_attributes=True) for location in locations]
