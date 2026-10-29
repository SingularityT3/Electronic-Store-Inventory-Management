"""Public service interface of the `stock` module."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal, Protocol

from sqlalchemy import any_, exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.audit import audit_service
from app.modules.notifications import reevaluate_stock_alert as save_stock_alert
from app.modules.product import (
    ProductStockItem,
    lock_product_for_stock,
    product_stock_item,
    product_stock_items,
)
from app.modules.stock._internal.models import (
    Batch,
    BatchReceipt,
    BatchStock,
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


@dataclass(frozen=True)
class BatchAllocation:
    batch_stock_id: int
    batch_number: str
    quantity: int


@dataclass(frozen=True)
class BatchStockPosition:
    batch_stock_id: int
    batch_id: int
    batch_number: str
    product_id: int
    variant_id: int | None
    location_id: int
    quantity_received: int
    quantity_on_hand: int


@dataclass(frozen=True)
class BatchReceiptReference:
    location_id: int
    reference_type: str
    reference_id: int
    quantity: int


@dataclass(frozen=True)
class BatchRecallData:
    batch_id: int
    product_id: int
    variant_id: int | None
    batch_number: str
    quantity_received: int
    locations: tuple[BatchStockPosition, ...]
    receipts: tuple[BatchReceiptReference, ...]


@dataclass(frozen=True)
class TrackedSaleResult:
    serial_number_ids: tuple[int, ...] = ()
    batch_allocations: tuple[BatchAllocation, ...] = ()


class StockTransferError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def has_tracking_history(db: Session, product_id: int) -> bool:
    return any(
        db.scalar(query) is not None
        for query in (
            select(Batch.id).where(Batch.product_id == product_id).limit(1),
            select(SerialNumber.id).where(SerialNumber.product_id == product_id).limit(1),
            select(StockLevel.id)
            .where(StockLevel.product_id == product_id, StockLevel.quantity > 0)
            .limit(1),
        )
    )


def _tracked_item(db: Session, product_id: int, variant_id: int | None) -> ProductStockItem:
    lock_product_for_stock(db, product_id)
    item = product_stock_item(db, product_id, variant_id)
    if item is None or not item.is_active:
        raise ValueError("Product or variant not found.")
    return item


def receive_batch_stock(
    db: Session,
    *,
    product_id: int,
    variant_id: int | None,
    location_id: int,
    batch_number: str,
    quantity: int,
    user_id: int,
    username: str,
    reference_type: str,
    reference_id: int,
) -> int:
    """Register a batch receipt and its aggregate stock in the caller's transaction."""
    item = _tracked_item(db, product_id, variant_id)
    batch_number = batch_number.strip()
    if item.tracking_mode != "batch":
        raise ValueError("Product is not configured for batch tracking.")
    if not batch_number or len(batch_number) > 100:
        raise ValueError("Batch number must contain between 1 and 100 characters.")
    if quantity <= 0:
        raise ValueError("Batch quantity must be positive.")
    if not reference_type.strip() or len(reference_type) > 50 or reference_id <= 0:
        raise ValueError("A valid receipt reference is required.")
    with db.begin_nested():
        db.execute(
            insert(Batch)
            .values(
                product_id=product_id,
                variant_id=variant_id,
                batch_number=batch_number,
            )
            .on_conflict_do_nothing(constraint="uq_batches_product_id_variant_id_batch_number")
        )
        batch = db.scalar(
            select(Batch)
            .where(
                Batch.product_id == product_id,
                Batch.variant_id.is_not_distinct_from(variant_id),
                Batch.batch_number == batch_number,
            )
            .with_for_update()
        )
        if batch is None:
            raise RuntimeError("Batch record was not available after receipt.")

        db.execute(
            insert(BatchStock)
            .values(batch_id=batch.id, location_id=location_id, quantity_on_hand=0)
            .on_conflict_do_nothing(constraint="uq_batch_stock_batch_id_location_id")
        )
        batch_stock = db.scalar(
            select(BatchStock)
            .where(BatchStock.batch_id == batch.id, BatchStock.location_id == location_id)
            .with_for_update()
        )
        if batch_stock is None:
            raise RuntimeError("Batch stock row was not available after insert.")
        receipt = db.scalar(
            select(BatchReceipt).where(
                BatchReceipt.batch_id == batch.id,
                BatchReceipt.location_id == location_id,
                BatchReceipt.reference_type == reference_type,
                BatchReceipt.reference_id == reference_id,
            )
        )
        if receipt is not None:
            return batch.id
        batch_stock.quantity_received += quantity
        batch_stock.quantity_on_hand += quantity
        db.add(
            BatchReceipt(
                batch_id=batch.id,
                location_id=location_id,
                reference_type=reference_type,
                reference_id=reference_id,
                quantity=quantity,
            )
        )
        update_stock(
            db,
            product_id=product_id,
            variant_id=variant_id,
            location_id=location_id,
            quantity_delta=quantity,
            movement_type="receipt",
            user_id=user_id,
            username=username,
            reference_type=reference_type,
            reference_id=reference_id,
            _allow_tracked=True,
        )
        return batch.id


def receive_serial_stock(
    db: Session,
    *,
    product_id: int,
    variant_id: int | None,
    location_id: int,
    serial_numbers: Sequence[str],
    damaged_serial_numbers: Sequence[str] = (),
    user_id: int,
    username: str,
    reference_type: str,
    reference_id: int,
) -> tuple[int, ...]:
    """Register accepted and damaged serial units; only accepted units increase stock."""
    item = _tracked_item(db, product_id, variant_id)
    cleaned = [serial.strip() for serial in serial_numbers]
    damaged = [serial.strip() for serial in damaged_serial_numbers]
    if item.tracking_mode != "serial":
        raise ValueError("Product is not configured for serial tracking.")
    if not cleaned and not damaged:
        raise ValueError("At least one non-empty serial number is required.")
    if any(not serial for serial in [*cleaned, *damaged]):
        raise ValueError("Serial numbers cannot be empty.")
    if any(len(serial) > 100 for serial in [*cleaned, *damaged]):
        raise ValueError("Serial numbers must be no longer than 100 characters.")
    all_serials = [*cleaned, *damaged]
    if len(all_serials) != len(set(all_serials)):
        raise ValueError("Duplicate serial number")
    if not reference_type.strip() or len(reference_type) > 50 or reference_id <= 0:
        raise ValueError("A valid receipt reference is required.")
    try:
        with db.begin_nested():
            accepted_rows = [
                SerialNumber(
                    serial_number=serial,
                    product_id=product_id,
                    variant_id=variant_id,
                    location_id=location_id,
                    status="in_stock",
                )
                for serial in cleaned
            ]
            damaged_rows = [
                SerialNumber(
                    serial_number=serial,
                    product_id=product_id,
                    variant_id=variant_id,
                    location_id=location_id,
                    status="damaged",
                )
                for serial in damaged
            ]
            serial_rows = [*accepted_rows, *damaged_rows]
            db.add_all(serial_rows)
            db.flush()
            if accepted_rows:
                update_stock(
                    db,
                    product_id=product_id,
                    variant_id=variant_id,
                    location_id=location_id,
                    quantity_delta=len(accepted_rows),
                    movement_type="receipt",
                    user_id=user_id,
                    username=username,
                    reference_type=reference_type,
                    reference_id=reference_id,
                    _allow_tracked=True,
                )
            return tuple(row.id for row in serial_rows)
    except IntegrityError as exc:
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint == "uq_serial_numbers_serial_number":
            raise ValueError("Duplicate serial number") from None
        raise


def update_average_unit_cost(
    db: Session,
    *,
    product_id: int,
    variant_id: int | None,
    quantity: int,
    unit_price: Decimal,
) -> Decimal:
    """Apply a receipt's accepted quantity to the item's weighted average cost."""
    if quantity <= 0 or unit_price < 0:
        raise ValueError("Receipt quantity must be positive and unit price nonnegative.")

    lock_product_for_stock(db, product_id)
    with db.begin_nested():
        db.execute(
            insert(ItemCost)
            .values(product_id=product_id, variant_id=variant_id, average_cost=None)
            .on_conflict_do_nothing()
        )
        item_cost = db.scalar(
            select(ItemCost)
            .where(
                ItemCost.product_id == product_id,
                ItemCost.variant_id.is_not_distinct_from(variant_id),
            )
            .with_for_update()
        )
        if item_cost is None:
            raise RuntimeError("Item cost row was not available after insert.")

        quantity_after = int(
            db.scalar(
                select(func.coalesce(func.sum(StockLevel.quantity), 0)).where(
                    StockLevel.product_id == product_id,
                    StockLevel.variant_id.is_not_distinct_from(variant_id),
                )
            )
        )
        quantity_before = quantity_after - quantity
        if quantity_before < 0:
            raise RuntimeError("Receipt quantity exceeds updated stock.")
        if item_cost.average_cost is None or quantity_before == 0:
            average_cost = unit_price
        else:
            average_cost = (
                item_cost.average_cost * quantity_before + unit_price * quantity
            ) / quantity_after
        item_cost.average_cost = average_cost.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        db.flush()
        return item_cost.average_cost


def consume_tracked_stock(
    db: Session,
    *,
    product_id: int,
    variant_id: int | None,
    location_id: int,
    quantity: int,
    serial_numbers: Sequence[str],
    user_id: int,
    username: str,
    sale_id: int,
) -> TrackedSaleResult:
    """Consume stock for a sale, locking the tracked units before changing aggregate stock."""
    item = _tracked_item(db, product_id, variant_id)
    if item.tracking_mode == "untracked":
        if serial_numbers:
            raise ValueError("Serial numbers are not accepted for an untracked product.")
        update_stock(
            db,
            product_id=product_id,
            variant_id=variant_id,
            location_id=location_id,
            quantity_delta=-quantity,
            movement_type="sale",
            user_id=user_id,
            username=username,
            reference_type="sale",
            reference_id=sale_id,
            record_audit=False,
        )
        return TrackedSaleResult()
    if item.tracking_mode == "serial":
        cleaned = [serial.strip() for serial in serial_numbers]
        if any(not serial or len(serial) > 100 for serial in cleaned):
            raise ValueError("Serial numbers must be non-empty and no longer than 100 characters.")
        if len(cleaned) != quantity:
            raise ValueError("Provide one serial number for each unit sold.")
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("Duplicate serial number")
        serial_rows = db.scalars(
            select(SerialNumber)
            .where(
                SerialNumber.serial_number.in_(cleaned),
                SerialNumber.product_id == product_id,
                SerialNumber.variant_id.is_not_distinct_from(variant_id),
                SerialNumber.location_id == location_id,
                SerialNumber.status.in_(("in_stock", "returned")),
            )
            .with_for_update()
        ).all()
        if len(serial_rows) != quantity:
            already_sold = db.scalar(
                select(SerialNumber.id)
                .where(
                    SerialNumber.serial_number.in_(cleaned),
                    SerialNumber.product_id == product_id,
                    SerialNumber.variant_id.is_not_distinct_from(variant_id),
                    SerialNumber.status == "sold",
                )
                .limit(1)
            )
            if already_sold is not None:
                raise ValueError("Duplicate serial number")
            raise ValueError("One or more serial numbers are not available at this location.")
        for serial in serial_rows:
            serial.status = "sold"
        update_stock(
            db,
            product_id=product_id,
            variant_id=variant_id,
            location_id=location_id,
            quantity_delta=-quantity,
            movement_type="sale",
            user_id=user_id,
            username=username,
            reference_type="sale",
            reference_id=sale_id,
            record_audit=False,
            _allow_tracked=True,
        )
        return TrackedSaleResult(serial_number_ids=tuple(row.id for row in serial_rows))

    allocations: list[BatchAllocation] = []
    remaining = quantity
    batch_rows = db.execute(
        select(BatchStock, Batch.batch_number)
        .join(Batch, Batch.id == BatchStock.batch_id)
        .where(
            Batch.product_id == product_id,
            Batch.variant_id.is_not_distinct_from(variant_id),
            BatchStock.location_id == location_id,
            BatchStock.quantity_on_hand > 0,
        )
        .order_by(Batch.created_at, Batch.id)
        .with_for_update(of=BatchStock)
    ).all()
    for batch_stock, batch_number in batch_rows:
        consumed = min(remaining, batch_stock.quantity_on_hand)
        if consumed:
            batch_stock.quantity_on_hand -= consumed
            allocations.append(BatchAllocation(batch_stock.id, batch_number, consumed))
            remaining -= consumed
        if remaining == 0:
            break
    if remaining:
        raise InsufficientStockError("Insufficient batch stock.")
    update_stock(
        db,
        product_id=product_id,
        variant_id=variant_id,
        location_id=location_id,
        quantity_delta=-quantity,
        movement_type="sale",
        user_id=user_id,
        username=username,
        reference_type="sale",
        reference_id=sale_id,
        record_audit=False,
        _allow_tracked=True,
    )
    return TrackedSaleResult(batch_allocations=tuple(allocations))


def move_tracked_stock(
    db: Session,
    *,
    product_id: int,
    variant_id: int | None,
    from_location_id: int,
    to_location_id: int,
    quantity: int,
) -> None:
    """Move serial locations or aggregate batch quantities with a stock transfer."""
    item = _tracked_item(db, product_id, variant_id)
    if item.tracking_mode == "untracked":
        return
    if item.tracking_mode == "serial":
        units = db.scalars(
            select(SerialNumber)
            .where(
                SerialNumber.product_id == product_id,
                SerialNumber.variant_id.is_not_distinct_from(variant_id),
                SerialNumber.location_id == from_location_id,
                SerialNumber.status.in_(("in_stock", "returned")),
            )
            .order_by(SerialNumber.id)
            .limit(quantity)
            .with_for_update()
        ).all()
        if len(units) != quantity:
            raise InsufficientStockError("Insufficient serial-tracked stock.")
        for unit in units:
            unit.location_id = to_location_id
        return

    remaining = quantity
    batch_rows = db.execute(
        select(BatchStock, Batch)
        .join(Batch, Batch.id == BatchStock.batch_id)
        .where(
            Batch.product_id == product_id,
            Batch.variant_id.is_not_distinct_from(variant_id),
            BatchStock.location_id == from_location_id,
            BatchStock.quantity_on_hand > 0,
        )
        .order_by(Batch.created_at, Batch.id)
        .with_for_update(of=BatchStock)
    ).all()
    for source, batch in batch_rows:
        moved = min(remaining, source.quantity_on_hand)
        if moved == 0:
            continue
        source.quantity_on_hand -= moved
        db.execute(
            insert(BatchStock)
            .values(batch_id=batch.id, location_id=to_location_id, quantity_on_hand=moved)
            .on_conflict_do_update(
                constraint="uq_batch_stock_batch_id_location_id",
                set_={
                    "quantity_on_hand": BatchStock.quantity_on_hand
                    + insert(BatchStock).excluded.quantity_on_hand
                },
            )
        )
        remaining -= moved
        if remaining == 0:
            break
    if remaining:
        raise InsufficientStockError("Insufficient batch-tracked stock.")


def restore_batch_stock(
    db: Session,
    *,
    batch_stock_id: int,
    location_id: int,
    quantity: int,
    user_id: int,
    username: str,
    return_line_id: int,
) -> None:
    batch_stock = db.scalar(
        select(BatchStock)
        .where(BatchStock.id == batch_stock_id, BatchStock.location_id == location_id)
        .with_for_update()
    )
    if batch_stock is None or quantity <= 0:
        raise ValueError("Batch stock allocation was not found.")
    batch = db.get(Batch, batch_stock.batch_id)
    if batch is None:
        raise RuntimeError("Batch record is missing.")
    batch_stock.quantity_on_hand += quantity
    update_stock(
        db,
        product_id=batch.product_id,
        variant_id=batch.variant_id,
        location_id=location_id,
        quantity_delta=quantity,
        movement_type="return",
        user_id=user_id,
        username=username,
        reference_type="return_line",
        reference_id=return_line_id,
        record_audit=False,
        _allow_inactive=True,
        _allow_tracked=True,
    )


def restore_serial_stock(
    db: Session,
    *,
    serial_number_ids: Sequence[int],
    location_id: int,
    user_id: int,
    username: str,
    return_line_id: int,
) -> None:
    serials = db.scalars(
        select(SerialNumber)
        .where(SerialNumber.id.in_(serial_number_ids))
        .order_by(SerialNumber.id)
        .with_for_update()
    ).all()
    if (
        not serial_number_ids
        or len(serial_number_ids) != len(set(serial_number_ids))
        or len(serials) != len(serial_number_ids)
    ):
        raise ValueError("Serial number was not found.")
    if any(serial.status != "sold" for serial in serials):
        raise ValueError("Serial number is not currently sold.")
    product_keys = {(serial.product_id, serial.variant_id) for serial in serials}
    if len(product_keys) != 1:
        raise ValueError("Returned serial numbers must belong to one product or variant.")
    product_id, variant_id = next(iter(product_keys))
    for serial in serials:
        serial.status = "returned"
        serial.location_id = location_id
    update_stock(
        db,
        product_id=product_id,
        variant_id=variant_id,
        location_id=location_id,
        quantity_delta=len(serials),
        movement_type="return",
        user_id=user_id,
        username=username,
        reference_type="return_line",
        reference_id=return_line_id,
        record_audit=False,
        _allow_inactive=True,
        _allow_tracked=True,
    )


def batch_stock_positions(
    db: Session, *, batch_id: int, location_id: int | None = None
) -> BatchRecallData | None:
    batch = db.get(Batch, batch_id)
    if batch is None:
        return None
    query = (
        select(BatchStock).where(BatchStock.batch_id == batch_id).order_by(BatchStock.location_id)
    )
    if location_id is not None:
        query = query.where(BatchStock.location_id == location_id)
    rows = [
        BatchStockPosition(
            batch_stock_id=row.id,
            batch_id=row.batch_id,
            batch_number=batch.batch_number,
            product_id=batch.product_id,
            variant_id=batch.variant_id,
            location_id=row.location_id,
            quantity_received=row.quantity_received,
            quantity_on_hand=row.quantity_on_hand,
        )
        for row in db.scalars(query)
    ]
    receipt_query = (
        select(BatchReceipt)
        .where(BatchReceipt.batch_id == batch_id)
        .order_by(BatchReceipt.created_at, BatchReceipt.id)
    )
    if location_id is not None:
        receipt_query = receipt_query.where(BatchReceipt.location_id == location_id)
    receipts = tuple(
        BatchReceiptReference(
            location_id=row.location_id,
            reference_type=row.reference_type,
            reference_id=row.reference_id,
            quantity=row.quantity,
        )
        for row in db.scalars(receipt_query)
    )
    return BatchRecallData(
        batch_id=batch.id,
        product_id=batch.product_id,
        variant_id=batch.variant_id,
        batch_number=batch.batch_number,
        quantity_received=sum(row.quantity_received for row in rows),
        locations=tuple(rows),
        receipts=receipts,
    )


def serial_number_labels(db: Session, serial_number_ids: Sequence[int]) -> dict[int, str]:
    if not serial_number_ids:
        return {}
    return {
        serial.id: serial.serial_number
        for serial in db.scalars(select(SerialNumber).where(SerialNumber.id.in_(serial_number_ids)))
    }


def stock_positions(
    db: Session,
    *,
    location_id: int | None = None,
    product_ids: Sequence[int] | None = None,
) -> list[StockPosition]:
    """Read live stock with product metadata and cost through owning module interfaces.

    Empty rows of deleted products and variants (and of a base product that now has
    variants) are left out; rows that still hold stock are always shown.
    """
    query = (
        select(StockLevel, Location.name)
        .join(Location, Location.id == StockLevel.location_id)
        .where(Location.is_active)
    )
    if location_id is not None:
        query = query.where(StockLevel.location_id == location_id)
    if product_ids is not None:
        ids = list(product_ids)
        if not ids:
            return []
        query = query.where(StockLevel.product_id.in_(ids))

    item_metadata: dict[tuple[int, int | None], ProductStockItem] = {
        (item.product_id, item.variant_id): item for item in product_stock_items(db, product_ids)
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
        if not item.is_active and level.quantity == 0:
            continue

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
    lock_product_for_stock(db, product_id)
    item = product_stock_item(db, product_id, variant_id)
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
    _allow_inactive: bool = False,
    _allow_tracked: bool = False,
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

    # Stock already held by an item that has since been deleted may still be taken out.
    lock_product_for_stock(db, product_id)
    item = product_stock_item(db, product_id, variant_id)
    if item is None or (quantity_delta > 0 and not item.is_active and not _allow_inactive):
        raise ValueError("Product or variant not found.")
    if item.tracking_mode != "untracked" and not _allow_tracked:
        raise ValueError("Tracked stock must be changed through the tracking service.")

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

            item = product_stock_item(db, product_id, variant_id)
            if item is None or not item.is_active:
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
            move_tracked_stock(
                db,
                product_id=product_id,
                variant_id=variant_id,
                from_location_id=from_location_id,
                to_location_id=to_location_id,
                quantity=quantity,
            )

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
                _allow_tracked=True,
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
                _allow_tracked=True,
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
        item = _tracked_item(db, product_id, variant_id)
        if item.tracking_mode != "untracked":
            if quantity_change > 0:
                raise StockAdjustmentError(
                    422, "Tracked stock must be registered through a receipt."
                )
            quantity_to_remove = -quantity_change
            if item.tracking_mode == "batch":
                batch_rows = db.scalars(
                    select(BatchStock)
                    .join(Batch, Batch.id == BatchStock.batch_id)
                    .where(
                        Batch.product_id == product_id,
                        Batch.variant_id.is_not_distinct_from(variant_id),
                        BatchStock.location_id == location_id,
                        BatchStock.quantity_on_hand > 0,
                    )
                    .order_by(Batch.created_at, Batch.id)
                    .with_for_update()
                ).all()
                remaining = quantity_to_remove
                for row in batch_rows:
                    removed = min(remaining, row.quantity_on_hand)
                    row.quantity_on_hand -= removed
                    remaining -= removed
                    if remaining == 0:
                        break
                if remaining:
                    raise StockAdjustmentError(409, "Adjustment would exceed tracked batch stock.")
            else:
                serials = db.scalars(
                    select(SerialNumber)
                    .where(
                        SerialNumber.product_id == product_id,
                        SerialNumber.variant_id.is_not_distinct_from(variant_id),
                        SerialNumber.location_id == location_id,
                        SerialNumber.status.in_(("in_stock", "returned")),
                    )
                    .order_by(SerialNumber.id)
                    .limit(quantity_to_remove)
                    .with_for_update()
                ).all()
                if len(serials) != quantity_to_remove:
                    raise StockAdjustmentError(409, "Adjustment would exceed tracked serial stock.")
                for serial in serials:
                    serial.status = "damaged" if reason_code == "damage" else "removed"
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
            _allow_tracked=True,
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

    def positions(
        self,
        db: Session,
        *,
        location_id: int | None = None,
        product_ids: Sequence[int] | None = None,
    ) -> list[StockPosition]: ...

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

    def update_average_unit_cost(
        self,
        db: Session,
        *,
        product_id: int,
        variant_id: int | None,
        quantity: int,
        unit_price: Decimal,
    ) -> Decimal: ...

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


def stock_quantities(
    db: Session,
    product_ids: int | Sequence[int],
    location_id: int | None = None,
    all_locations: bool = True,
) -> dict[int, dict[int | None, int]]:
    """Return batched on-hand quantities, optionally scoped to one location.

    `stock_levels` is the single count of on-hand stock (#18 makes `update_stock` the only
    path that changes it), so serialised units (#17) must be counted there when received and
    `serial_numbers` rows are not added on top.
    """
    ids = [product_ids] if isinstance(product_ids, int) else list(product_ids)
    if not ids:
        return {}
    # One array parameter, not one per id: sorting by stock looks up every product at once.
    stock_filter = [StockLevel.product_id == any_(ids)]
    if not all_locations:
        stock_filter.append(StockLevel.location_id == location_id)
    rows = db.execute(
        select(StockLevel.variant_id, func.coalesce(func.sum(StockLevel.quantity), 0))
        .add_columns(StockLevel.product_id)
        .where(*stock_filter)
        .group_by(StockLevel.product_id, StockLevel.variant_id)
    )
    quantities: dict[int, dict[int | None, int]] = {}
    for variant_id, quantity, product_id in rows:
        quantities.setdefault(product_id, {})[variant_id] = int(quantity)
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


def location_name(db: Session, location_id: int) -> str | None:
    """Return an active location's name, for labelling report filters."""
    return db.scalar(select(Location.name).where(Location.id == location_id, Location.is_active))
