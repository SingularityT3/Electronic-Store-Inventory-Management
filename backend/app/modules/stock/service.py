"""Public service interface of the `stock` module."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from sqlalchemy import exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.modules.audit import audit_service
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

    with db.begin_nested():
        locations = db.scalars(
            select(Location)
            .where(Location.id.in_((from_location_id, to_location_id)), Location.is_active)
            .order_by(Location.id)
            .with_for_update()
        ).all()
        if len(locations) != 2:
            raise StockTransferError(404, "An active source or destination location was not found.")

        item_exists = any(
            item.product_id == product_id and item.variant_id == variant_id
            for item in product_stock_items(db)
        )
        if not item_exists:
            raise StockTransferError(404, "Product or variant not found.")

        for location_id in sorted((from_location_id, to_location_id)):
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

        levels = db.scalars(
            select(StockLevel)
            .where(
                StockLevel.product_id == product_id,
                StockLevel.variant_id == variant_id,
                StockLevel.location_id.in_((from_location_id, to_location_id)),
            )
            .order_by(StockLevel.location_id)
            .with_for_update()
        ).all()
        levels_by_location = {level.location_id: level for level in levels}
        source = levels_by_location[from_location_id]
        destination = levels_by_location[to_location_id]

        if source.quantity < quantity:
            raise StockTransferError(409, "Insufficient stock at the source location.")

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

        source_before = source.quantity
        destination_before = destination.quantity
        source.quantity -= quantity
        destination.quantity += quantity
        db.add_all(
            [
                StockMovement(
                    product_id=product_id,
                    variant_id=variant_id,
                    location_id=from_location_id,
                    quantity_change=-quantity,
                    movement_type="transfer_out",
                    reference_type="stock_transfer",
                    reference_id=transfer.id,
                    user_id=user_id,
                ),
                StockMovement(
                    product_id=product_id,
                    variant_id=variant_id,
                    location_id=to_location_id,
                    quantity_change=quantity,
                    movement_type="transfer_in",
                    reference_type="stock_transfer",
                    reference_id=transfer.id,
                    user_id=user_id,
                ),
            ]
        )
        db.flush()
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
                "from_quantity": source_before,
                "to_quantity": destination_before,
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


class StockService(Protocol):
    """Operations the `stock` module offers to other modules.

    Methods are added as features land; callers depend on this interface,
    never on `_internal`.
    """

    def positions(self, db: Session, *, location_id: int | None = None) -> list[StockPosition]: ...

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


def stock_quantities(db: Session, product_id: int) -> dict[int | None, int]:
    """Return on-hand quantities separately for the base product and each variant."""
    rows = db.execute(
        select(
            StockLevel.variant_id,
            func.coalesce(func.sum(StockLevel.quantity), 0),
        )
        .where(StockLevel.product_id == product_id)
        .group_by(StockLevel.variant_id)
    )
    quantities = {variant_id: int(quantity) for variant_id, quantity in rows}

    serial_rows = db.execute(
        select(SerialNumber.variant_id, func.count())
        .where(
            SerialNumber.product_id == product_id,
            SerialNumber.status == "in_stock",
        )
        .group_by(SerialNumber.variant_id)
    )
    for variant_id, quantity in serial_rows:
        quantities[variant_id] = quantities.get(variant_id, 0) + int(quantity)

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
