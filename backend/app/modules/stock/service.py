"""Public service interface of the `stock` module."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal, Protocol

from sqlalchemy import exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.modules.audit import audit_service
from app.modules.notifications import reevaluate_stock_alert as save_stock_alert
from app.modules.product import ProductStockItem, product_stock_items
from app.modules.stock._internal.models import (
    ItemCost,
    Location,
    SerialNumber,
    StockLevel,
    StockMovement,
    StockTransfer,
)


@dataclass(frozen=True)
class StockPosition:
    """A stock quantity and its display/reorder/valuation data for one active location."""

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
    reorder_threshold: int
    reorder_to_level: int
    average_cost: Decimal | None


MovementType = Literal[
    "initial", "receipt", "sale", "return", "transfer_in", "transfer_out", "adjustment"
]
ReasonCode = Literal["damage", "loss", "correction"]


@dataclass(frozen=True)
class StockUpdateResult:
    product_id: int
    variant_id: int | None
    location_id: int
    quantity_delta: int
    previous_quantity: int
    quantity: int


class InsufficientStockError(Exception):
    """Raised when an update would leave a location with negative stock."""


@dataclass(frozen=True)
class StockTransferResult:
    id: int
    product_id: int
    variant_id: int | None
    from_location_id: int
    to_location_id: int
    quantity: int
    created_at: datetime


class StockTransferError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def stock_positions(db: Session, *, location_id: int | None = None) -> list[StockPosition]:
    """Read live stock with product metadata and cost through owning module interfaces."""
    query = (
        select(StockLevel, Location.name)
        .join(Location, Location.id == StockLevel.location_id)
        .where(Location.is_active)
    )
    if location_id is not None:
        query = query.where(StockLevel.location_id == location_id)

    item_metadata: dict[tuple[int, int | None], ProductStockItem] = {
        (item.product_id, item.variant_id): item for item in product_stock_items(db)
    }
    costs = {
        (product_id, variant_id): average_cost
        for product_id, variant_id, average_cost in db.execute(
            select(ItemCost.product_id, ItemCost.variant_id, ItemCost.average_cost)
        )
    }

    positions = []
    for level, location_name in db.execute(query.order_by(Location.name, StockLevel.id)):
        key = (level.product_id, level.variant_id)
        item = item_metadata.get(key)
        if item is None:
            raise RuntimeError(f"Missing product metadata for stock item {key}.")

        positions.append(
            StockPosition(
                product_id=item.product_id,
                product_name=item.product_name,
                sku=item.sku,
                category_id=item.category_id,
                category_name=item.category_name,
                variant_id=item.variant_id,
                variant_sku=item.variant_sku,
                variant_attributes=item.variant_attributes,
                location_id=level.location_id,
                location_name=location_name,
                quantity=level.quantity,
                reorder_threshold=level.reorder_threshold,
                reorder_to_level=(
                    level.reorder_to_level
                    if level.reorder_to_level is not None
                    else 2 * level.reorder_threshold
                ),
                average_cost=costs.get(key),
            )
        )

    return positions


def reevaluate_stock_alert(
    db: Session, *, product_id: int, variant_id: int | None, location_id: int
) -> None:
    """Reevaluate an item's alert after its stock level changes."""
    row = db.execute(
        select(StockLevel, Location.name)
        .join(Location, Location.id == StockLevel.location_id)
        .where(
            StockLevel.product_id == product_id,
            StockLevel.variant_id.is_not_distinct_from(variant_id),
            StockLevel.location_id == location_id,
            Location.is_active,
        )
        .with_for_update(of=StockLevel)
    ).one_or_none()
    if row is None:
        return

    level, location_name = row
    item = next(
        (
            item
            for item in product_stock_items(db)
            if item.product_id == product_id and item.variant_id == variant_id
        ),
        None,
    )
    if item is None:
        raise RuntimeError(f"Missing product metadata for stock item {(product_id, variant_id)}.")

    save_stock_alert(
        db,
        product_id=product_id,
        variant_id=variant_id,
        product_name=item.product_name,
        sku=item.sku,
        variant_sku=item.variant_sku,
        location_id=location_id,
        location_name=location_name,
        quantity=level.quantity,
        threshold=level.reorder_threshold,
    )


def update_stock(
    db: Session,
    *,
    product_id: int,
    variant_id: int | None,
    location_id: int,
    quantity_delta: int,
    movement_type: MovementType,
    user_id: int | None = None,
    username: str | None = None,
    reason_code: ReasonCode | None = None,
    reason: str | None = None,
    reference_type: str | None = None,
    reference_id: int | None = None,
    record_audit: bool = True,
) -> StockUpdateResult:
    """Apply one stock delta and its movement/audit in the caller's transaction."""
    if quantity_delta == 0:
        raise ValueError("Stock quantity delta must not be zero.")
    if movement_type not in {
        "initial",
        "receipt",
        "sale",
        "return",
        "transfer_in",
        "transfer_out",
        "adjustment",
    }:
        raise ValueError(f"Unsupported stock movement type: {movement_type}.")
    if movement_type in {"initial", "receipt", "return", "transfer_in"} and quantity_delta < 0:
        raise ValueError(f"{movement_type} movements must increase stock.")
    if movement_type in {"sale", "transfer_out"} and quantity_delta > 0:
        raise ValueError(f"{movement_type} movements must decrease stock.")

    item_exists = any(
        item.product_id == product_id and item.variant_id == variant_id
        for item in product_stock_items(db)
    )
    if not item_exists:
        raise ValueError("Product or variant not found.")

    with db.begin_nested():
        if quantity_delta > 0:
            db.execute(
                insert(StockLevel)
                .values(
                    product_id=product_id,
                    variant_id=variant_id,
                    location_id=location_id,
                    quantity=0,
                )
                .on_conflict_do_nothing(
                    constraint="uq_stock_levels_product_id_variant_id_location_id"
                )
            )

        level = db.scalar(
            select(StockLevel)
            .where(
                StockLevel.product_id == product_id,
                StockLevel.variant_id == variant_id,
                StockLevel.location_id == location_id,
            )
            .with_for_update()
        )
        if level is None or level.quantity + quantity_delta < 0:
            raise InsufficientStockError("Insufficient stock.")

        previous_quantity = level.quantity
        level.quantity += quantity_delta
        db.add(
            StockMovement(
                product_id=product_id,
                variant_id=variant_id,
                location_id=location_id,
                quantity_change=quantity_delta,
                movement_type=movement_type,
                reason_code=reason_code,
                reason=reason,
                reference_type=reference_type,
                reference_id=reference_id,
                user_id=user_id,
            )
        )
        db.flush()

        if record_audit:
            audit_service.record(
                db,
                module="stock",
                action="stock_updated",
                user_id=user_id,
                username=username,
                entity_type="stock_level",
                entity_id=f"{product_id}:{variant_id}:{location_id}",
                details=(
                    f"Updated stock for product {product_id} at location {location_id} "
                    f"by {quantity_delta} ({movement_type})."
                    + (f" Reason: {reason.strip()}" if reason else "")
                ),
                before={"quantity": previous_quantity},
                after={
                    "quantity": level.quantity,
                    "quantity_delta": quantity_delta,
                    **({"reason_code": reason_code, "reason": reason.strip()} if reason else {}),
                },
            )
            db.flush()

        reevaluate_stock_alert(
            db,
            product_id=product_id,
            variant_id=variant_id,
            location_id=location_id,
        )
        return StockUpdateResult(
            product_id=product_id,
            variant_id=variant_id,
            location_id=location_id,
            quantity_delta=quantity_delta,
            previous_quantity=previous_quantity,
            quantity=level.quantity,
        )


def transfer_stock(
    db: Session,
    *,
    product_id: int,
    variant_id: int | None,
    from_location_id: int,
    to_location_id: int,
    quantity: int,
    user_id: int,
    username: str,
) -> StockTransferResult:
    """Atomically transfer on-hand stock, movements, and audit data between locations."""
    if quantity <= 0:
        raise StockTransferError(422, "Transfer quantity must be positive.")
    if from_location_id == to_location_id:
        raise StockTransferError(422, "Source and destination locations must be different.")

    try:
        with db.begin_nested():
            locations = db.scalars(
                select(Location)
                .where(Location.id.in_((from_location_id, to_location_id)), Location.is_active)
                .order_by(Location.id)
                .with_for_update()
            ).all()
            if len(locations) != 2:
                raise StockTransferError(
                    404, "An active source or destination location was not found."
                )

            item_exists = any(
                item.product_id == product_id and item.variant_id == variant_id
                for item in product_stock_items(db)
            )
            if not item_exists:
                raise StockTransferError(404, "Product or variant not found.")

            transfer = StockTransfer(
                product_id=product_id,
                variant_id=variant_id,
                from_location_id=from_location_id,
                to_location_id=to_location_id,
                quantity=quantity,
                user_id=user_id,
            )
            db.add(transfer)
            db.flush()

            source = update_stock(
                db,
                product_id=product_id,
                variant_id=variant_id,
                location_id=from_location_id,
                quantity_delta=-quantity,
                movement_type="transfer_out",
                user_id=user_id,
                username=username,
                reference_type="stock_transfer",
                reference_id=transfer.id,
                record_audit=False,
            )
            destination = update_stock(
                db,
                product_id=product_id,
                variant_id=variant_id,
                location_id=to_location_id,
                quantity_delta=quantity,
                movement_type="transfer_in",
                user_id=user_id,
                username=username,
                reference_type="stock_transfer",
                reference_id=transfer.id,
                record_audit=False,
            )

            audit_service.record(
                db,
                module="stock",
                action="stock_transferred",
                user_id=user_id,
                username=username,
                entity_type="stock_transfer",
                entity_id=str(transfer.id),
                details=(
                    f"Transferred {quantity} units of product {product_id} "
                    f"from location {from_location_id} to location {to_location_id}."
                ),
                before={
                    "from_quantity": source.previous_quantity,
                    "to_quantity": destination.previous_quantity,
                },
                after={
                    "from_quantity": source.quantity,
                    "to_quantity": destination.quantity,
                },
            )
            db.flush()

            return StockTransferResult(
                id=transfer.id,
                product_id=product_id,
                variant_id=variant_id,
                from_location_id=from_location_id,
                to_location_id=to_location_id,
                quantity=quantity,
                created_at=transfer.created_at,
            )
    except InsufficientStockError as exc:
        raise StockTransferError(409, "Insufficient stock at the source location.") from exc


class StockAdjustmentError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def adjust_stock(
    db: Session,
    *,
    product_id: int,
    variant_id: int | None,
    location_id: int,
    quantity_change: int,
    reason: str,
    reason_code: ReasonCode = "correction",
    user_id: int,
    username: str,
) -> StockUpdateResult:
    """Apply a manual stock adjustment (FR-2.4); the reason is mandatory."""
    if not reason or not reason.strip():
        raise StockAdjustmentError(422, "Reason is required for stock adjustment")
    if quantity_change == 0:
        raise StockAdjustmentError(422, "Adjustment quantity must not be zero.")
    if not db.scalar(select(exists().where(Location.id == location_id, Location.is_active))):
        raise StockAdjustmentError(404, "Location not found.")
    try:
        return update_stock(
            db,
            product_id=product_id,
            variant_id=variant_id,
            location_id=location_id,
            quantity_delta=quantity_change,
            movement_type="adjustment",
            user_id=user_id,
            username=username,
            reason_code=reason_code,
            reason=reason.strip(),
        )
    except InsufficientStockError as exc:
        raise StockAdjustmentError(409, "Adjustment would result in negative stock") from exc
    except ValueError as exc:
        raise StockAdjustmentError(404, "Product or variant not found.") from exc


class StockService(Protocol):
    """Operations the `stock` module offers to other modules.

    Methods are added as features land; callers depend on this interface,
    never on `_internal`.
    """

    def positions(self, db: Session, *, location_id: int | None = None) -> list[StockPosition]: ...

    def reevaluate_stock_alert(
        self, db: Session, *, product_id: int, variant_id: int | None, location_id: int
    ) -> None: ...

    def update(
        self,
        db: Session,
        *,
        product_id: int,
        variant_id: int | None,
        location_id: int,
        quantity_delta: int,
        movement_type: MovementType,
        user_id: int | None = None,
        username: str | None = None,
        reason_code: ReasonCode | None = None,
        reason: str | None = None,
        reference_type: str | None = None,
        reference_id: int | None = None,
        record_audit: bool = True,
    ) -> StockUpdateResult: ...

    def transfer(
        self,
        db: Session,
        *,
        product_id: int,
        variant_id: int | None,
        from_location_id: int,
        to_location_id: int,
        quantity: int,
        user_id: int,
        username: str,
    ) -> StockTransferResult: ...


def has_stock(db: Session, product_id: int) -> bool:
    """Return whether a product or variant has stock on hand."""
    return bool(
        db.scalar(
            select(
                exists().where(
                    StockLevel.product_id == product_id,
                    StockLevel.quantity > 0,
                )
            )
        )
        or db.scalar(
            select(
                exists().where(
                    SerialNumber.product_id == product_id,
                    SerialNumber.status == "in_stock",
                )
            )
        )
    )


def stock_quantities(
    db: Session,
    product_ids: int | Sequence[int],
    location_id: int | None = None,
    all_locations: bool = True,
) -> dict[int, dict[int | None, int]]:
    """Return batched on-hand quantities, optionally scoped to one location."""
    ids = [product_ids] if isinstance(product_ids, int) else list(product_ids)
    if not ids:
        return {}
    stock_filter = [StockLevel.product_id.in_(ids)]
    serial_filter = [
        SerialNumber.product_id.in_(ids),
        SerialNumber.status == "in_stock",
    ]
    if not all_locations:
        stock_filter.append(StockLevel.location_id == location_id)
        serial_filter.append(SerialNumber.location_id == location_id)
    rows = db.execute(
        select(StockLevel.variant_id, func.coalesce(func.sum(StockLevel.quantity), 0))
        .add_columns(StockLevel.product_id)
        .where(*stock_filter)
        .group_by(StockLevel.product_id, StockLevel.variant_id)
    )
    quantities: dict[int, dict[int | None, int]] = {}
    for variant_id, quantity, product_id in rows:
        quantities.setdefault(product_id, {})[variant_id] = int(quantity)
    serial_rows = db.execute(
        select(SerialNumber.variant_id, func.count())
        .add_columns(SerialNumber.product_id)
        .where(*serial_filter)
        .group_by(SerialNumber.product_id, SerialNumber.variant_id)
    )
    for variant_id, quantity, product_id in serial_rows:
        product_quantities = quantities.setdefault(product_id, {})
        product_quantities[variant_id] = product_quantities.get(variant_id, 0) + int(quantity)
    return quantities


def location_exists(db: Session, location_id: int) -> bool:
    """Validate a location without exposing the stock table to auth."""
    return (
        db.scalar(
            select(Location.id).where(
                Location.id == location_id,
                Location.is_active,
            )
        )
        is not None
    )
