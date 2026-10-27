"""Purchase order creation, tracking and lifecycle routes."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_session
from app.modules.audit import audit_service
from app.modules.auth import (
    CurrentUser,
    Permission,
    authorize_location,
    po_status_notification_recipients,
    require,
)
from app.modules.notifications import record_purchase_order_status
from app.modules.product import product_stock_items
from app.modules.purchasing._internal.models import (
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseOrderReceipt,
    PurchaseOrderReceiptLine,
    PurchaseOrderReceiptSerial,
    Supplier,
    SupplierPriceHistory,
    SupplierProduct,
)
from app.modules.purchasing.service import update_purchase_order_receipt_status
from app.modules.stock import (
    InsufficientStockError,
    location_exists,
    receive_batch_stock,
    receive_serial_stock,
    update_average_unit_cost,
    update_stock,
)

router = APIRouter(prefix="/purchase-orders", tags=["purchase orders"])
DbSession = Annotated[Session, Depends(get_session)]
Status = Literal["draft", "submitted", "partially_received", "received", "cancelled"]
PENDING_STATUSES = ("draft", "submitted", "partially_received")


class PurchaseOrderLineInput(BaseModel):
    product_id: int = Field(ge=1)
    variant_id: int | None = Field(default=None, ge=1)
    quantity_ordered: int = Field(gt=0)
    unit_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class PurchaseOrderCreate(BaseModel):
    supplier_id: int = Field(ge=1)
    location_id: int = Field(ge=1)
    expected_delivery_date: date
    notes: str | None = None
    lines: list[PurchaseOrderLineInput] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_line_items(self) -> "PurchaseOrderCreate":
        identities = [(line.product_id, line.variant_id) for line in self.lines]
        if len(identities) != len(set(identities)):
            raise ValueError("A product or variant may appear only once per purchase order.")
        return self


class PurchaseOrderUpdate(BaseModel):
    supplier_id: int | None = Field(default=None, ge=1)
    location_id: int | None = Field(default=None, ge=1)
    expected_delivery_date: date | None = None
    notes: str | None = None
    lines: list[PurchaseOrderLineInput] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def unique_line_items(self) -> "PurchaseOrderUpdate":
        if self.lines is not None:
            identities = [(line.product_id, line.variant_id) for line in self.lines]
            if len(identities) != len(set(identities)):
                raise ValueError("A product or variant may appear only once per purchase order.")
        return self


class PurchaseOrderReceiptLineInput(BaseModel):
    po_line_id: int = Field(ge=1)
    quantity_accepted: int = Field(default=0, ge=0)
    quantity_damaged: int = Field(default=0, ge=0)
    quantity_short: int = Field(default=0, ge=0)
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    discrepancy_note: str | None = Field(default=None, max_length=2000)
    batch_number: str | None = Field(default=None, max_length=100)
    serial_numbers: list[str] = Field(default_factory=list)
    damaged_serial_numbers: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_discrepancy(self) -> "PurchaseOrderReceiptLineInput":
        if self.quantity_accepted + self.quantity_damaged + self.quantity_short == 0:
            raise ValueError("Enter an accepted, damaged, or short quantity.")
        if (self.quantity_damaged or self.quantity_short) and not (
            self.discrepancy_note and self.discrepancy_note.strip()
        ):
            raise ValueError("A discrepancy note is required for damaged or short quantities.")
        if self.batch_number is not None:
            self.batch_number = self.batch_number.strip() or None
        if self.discrepancy_note is not None:
            self.discrepancy_note = self.discrepancy_note.strip() or None
        return self


class PurchaseOrderReceiptInput(BaseModel):
    notes: str | None = None
    lines: list[PurchaseOrderReceiptLineInput] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_po_lines(self) -> "PurchaseOrderReceiptInput":
        line_ids = [line.po_line_id for line in self.lines]
        if len(line_ids) != len(set(line_ids)):
            raise ValueError("A purchase order line may appear only once per receipt.")
        return self


class PurchaseOrderLineOut(BaseModel):
    id: int
    product_id: int
    product_name: str
    sku: str
    variant_id: int | None
    tracking_mode: Literal["untracked", "batch", "serial"]
    quantity_ordered: int
    quantity_received: int
    quantity_outstanding: int
    unit_price: Decimal
    line_total: Decimal


class PurchaseOrderOut(BaseModel):
    id: int
    po_number: str
    supplier_id: int
    supplier_name: str
    location_id: int
    status: Status
    created_by: int
    notes: str | None
    expected_delivery_date: date | None
    submitted_at: datetime | None
    created_at: datetime
    lines: list[PurchaseOrderLineOut]
    total: Decimal


def _order_or_404(db: Session, order_id: int, *, lock: bool = False) -> PurchaseOrder:
    query = select(PurchaseOrder).where(PurchaseOrder.id == order_id)
    if lock:
        query = query.with_for_update()
    order = db.scalar(query)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Purchase order not found.")
    return order


def _ensure_active_supplier(db: Session, supplier_id: int) -> Supplier:
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Supplier not found.")
    if not supplier.is_active:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Supplier is inactive.")
    return supplier


def _validate_location(db: Session, location_id: int) -> None:
    if not location_exists(db, location_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Active receiving location not found.")


def _validate_catalog_lines(
    db: Session, supplier_id: int, lines: list[PurchaseOrderLineInput]
) -> None:
    active_items = {
        (item.product_id, item.variant_id)
        for item in product_stock_items(db, {line.product_id for line in lines})
        if item.is_active
    }
    for line in lines:
        identity = (line.product_id, line.variant_id)
        if identity not in active_items:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                "Product or variant not found.",
            )
        catalog_item = db.scalar(
            select(SupplierProduct.id).where(
                SupplierProduct.supplier_id == supplier_id,
                SupplierProduct.product_id == line.product_id,
                SupplierProduct.variant_id.is_not_distinct_from(line.variant_id),
            )
        )
        if catalog_item is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Product or variant is not in the selected supplier catalog.",
            )


Labels = dict[tuple[int, int | None], tuple[str, str, Literal["untracked", "batch", "serial"]]]


def _product_labels(db: Session, product_ids: set[int] | None = None) -> Labels:
    return {
        (item.product_id, item.variant_id): (
            item.product_name,
            item.variant_sku or item.sku,
            item.tracking_mode,
        )
        for item in product_stock_items(db, product_ids)
    }


def _line_out(line: PurchaseOrderLine, labels: Labels) -> PurchaseOrderLineOut:
    product_name, sku, tracking_mode = labels[(line.product_id, line.variant_id)]
    return PurchaseOrderLineOut(
        id=line.id,
        product_id=line.product_id,
        product_name=product_name,
        sku=sku,
        variant_id=line.variant_id,
        tracking_mode=tracking_mode,
        quantity_ordered=line.quantity_ordered,
        quantity_received=line.quantity_received,
        quantity_outstanding=line.quantity_ordered - line.quantity_received,
        unit_price=line.unit_price,
        line_total=line.unit_price * line.quantity_ordered,
    )


def _out(db: Session, order: PurchaseOrder, labels: Labels | None = None) -> PurchaseOrderOut:
    supplier = db.get(Supplier, order.supplier_id)
    if supplier is None:
        raise RuntimeError(f"Purchase order {order.id} has no supplier.")
    lines = db.scalars(
        select(PurchaseOrderLine)
        .where(PurchaseOrderLine.purchase_order_id == order.id)
        .order_by(PurchaseOrderLine.id)
    ).all()
    if labels is None:
        labels = _product_labels(db, {line.product_id for line in lines})
    missing = [
        (line.product_id, line.variant_id)
        for line in lines
        if (line.product_id, line.variant_id) not in labels
    ]
    if missing:
        raise RuntimeError(f"Missing product metadata for purchase order items: {missing}.")
    line_outputs = [_line_out(line, labels) for line in lines]
    return PurchaseOrderOut(
        id=order.id,
        po_number=order.po_number,
        supplier_id=order.supplier_id,
        supplier_name=supplier.name,
        location_id=order.location_id,
        status=order.status,
        created_by=order.created_by,
        notes=order.notes,
        expected_delivery_date=order.expected_delivery_date,
        submitted_at=order.submitted_at,
        created_at=order.created_at,
        lines=line_outputs,
        total=sum((line.line_total for line in line_outputs), Decimal(0)),
    )


def _record_status_change(
    db: Session, order: PurchaseOrder, actor: CurrentUser, previous_status: str
) -> None:
    audit_service.record(
        db,
        module="purchasing",
        action="purchase_order_status_changed",
        user_id=actor.id,
        username=actor.username,
        entity_type="purchase_order",
        entity_id=str(order.id),
        before={"status": previous_status},
        after={"status": order.status},
    )
    record_purchase_order_status(
        db,
        recipient_ids=po_status_notification_recipients(db, created_by_id=order.created_by),
        purchase_order_id=order.id,
        po_number=order.po_number,
        status=order.status,
    )


def _record_order_change(
    db: Session,
    order: PurchaseOrder,
    actor: CurrentUser,
    action: str,
    before: dict[str, Any] | None,
    after: dict[str, Any],
) -> None:
    audit_service.record(
        db,
        module="purchasing",
        action=action,
        user_id=actor.id,
        username=actor.username,
        entity_type="purchase_order",
        entity_id=str(order.id),
        before=before,
        after=after,
    )


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise


def _receipt_started(db: Session, order: PurchaseOrder) -> bool:
    if db.scalar(
        select(PurchaseOrderReceipt.id)
        .where(PurchaseOrderReceipt.purchase_order_id == order.id)
        .limit(1)
    ):
        return True
    return bool(
        db.scalar(
            select(PurchaseOrderLine.id)
            .where(
                PurchaseOrderLine.purchase_order_id == order.id,
                PurchaseOrderLine.quantity_received > 0,
            )
            .limit(1)
        )
    )


@router.get("", response_model=list[PurchaseOrderOut])
def list_purchase_orders(
    db: DbSession,
    _user: Annotated[CurrentUser, Depends(require(Permission.PURCHASE_ORDERS_MANAGE))],
    order_status: Status | None = None,
) -> list[PurchaseOrderOut]:
    query = select(PurchaseOrder).order_by(PurchaseOrder.created_at.desc(), PurchaseOrder.id.desc())
    if order_status is not None:
        query = query.where(PurchaseOrder.status == order_status)
    labels = _product_labels(db)
    return [_out(db, order, labels) for order in db.scalars(query)]


@router.get("/pending", response_model=list[PurchaseOrderOut])
def pending_purchase_orders(
    db: DbSession,
    _user: Annotated[CurrentUser, Depends(require(Permission.PURCHASE_ORDERS_MANAGE))],
) -> list[PurchaseOrderOut]:
    query = (
        select(PurchaseOrder)
        .where(PurchaseOrder.status.in_(PENDING_STATUSES))
        .order_by(PurchaseOrder.created_at.desc(), PurchaseOrder.id.desc())
    )
    labels = _product_labels(db)
    return [_out(db, order, labels) for order in db.scalars(query)]


@router.get("/receivable", response_model=list[PurchaseOrderOut])
def receivable_purchase_orders(
    db: DbSession,
    user: Annotated[CurrentUser, Depends(require(Permission.PURCHASE_ORDERS_RECEIVE))],
) -> list[PurchaseOrderOut]:
    query = (
        select(PurchaseOrder)
        .where(PurchaseOrder.status.in_(("submitted", "partially_received")))
        .order_by(PurchaseOrder.created_at.desc(), PurchaseOrder.id.desc())
    )
    if not user.sees_all_locations:
        if user.location_id is None:
            return []
        query = query.where(PurchaseOrder.location_id == user.location_id)
    labels = _product_labels(db)
    return [_out(db, order, labels) for order in db.scalars(query)]


@router.post("", response_model=PurchaseOrderOut, status_code=status.HTTP_201_CREATED)
def create_purchase_order(
    body: PurchaseOrderCreate,
    db: DbSession,
    user: Annotated[CurrentUser, Depends(require(Permission.PURCHASE_ORDERS_MANAGE))],
) -> PurchaseOrderOut:
    supplier = _ensure_active_supplier(db, body.supplier_id)
    _validate_location(db, body.location_id)
    _validate_catalog_lines(db, supplier.id, body.lines)
    order = PurchaseOrder(
        po_number=f"PO-{date.today():%Y%m%d}-{uuid4().hex[:8].upper()}",
        supplier_id=supplier.id,
        location_id=body.location_id,
        created_by=user.id,
        expected_delivery_date=body.expected_delivery_date,
        notes=body.notes.strip() if body.notes else None,
        status="draft",
    )
    db.add(order)
    db.flush()
    for line in body.lines:
        db.add(
            PurchaseOrderLine(
                purchase_order_id=order.id,
                product_id=line.product_id,
                variant_id=line.variant_id,
                quantity_ordered=line.quantity_ordered,
                unit_price=line.unit_price,
            )
        )
    db.flush()
    _record_order_change(
        db,
        order,
        user,
        "purchase_order_created",
        None,
        {
            "po_number": order.po_number,
            "supplier_id": order.supplier_id,
            "location_id": order.location_id,
            "expected_delivery_date": order.expected_delivery_date.isoformat(),
            "status": order.status,
            "lines": [
                {
                    "product_id": line.product_id,
                    "variant_id": line.variant_id,
                    "quantity_ordered": line.quantity_ordered,
                    "unit_price": str(line.unit_price),
                }
                for line in body.lines
            ],
        },
    )
    _commit(db)
    db.refresh(order)
    return _out(db, order)


@router.get("/{order_id}", response_model=PurchaseOrderOut)
def get_purchase_order(
    order_id: int,
    db: DbSession,
    _user: Annotated[CurrentUser, Depends(require(Permission.PURCHASE_ORDERS_MANAGE))],
) -> PurchaseOrderOut:
    return _out(db, _order_or_404(db, order_id))


@router.post("/{order_id}/receive", response_model=PurchaseOrderOut)
def receive_purchase_order(
    order_id: int,
    body: PurchaseOrderReceiptInput,
    db: DbSession,
    user: Annotated[CurrentUser, Depends(require(Permission.PURCHASE_ORDERS_RECEIVE))],
) -> PurchaseOrderOut:
    order = _order_or_404(db, order_id, lock=True)
    if order.status not in {"submitted", "partially_received"}:
        raise HTTPException(status.HTTP_409_CONFLICT, "Purchase order is not open for receiving.")
    authorize_location(db, user, order.location_id, "receive purchase order")

    po_lines = db.scalars(
        select(PurchaseOrderLine)
        .where(PurchaseOrderLine.purchase_order_id == order.id)
        .order_by(PurchaseOrderLine.id)
        .with_for_update()
    ).all()
    po_lines_by_id = {line.id: line for line in po_lines}
    for receipt_line in body.lines:
        po_line = po_lines_by_id.get(receipt_line.po_line_id)
        if po_line is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Purchase order line not found.")
        outstanding = po_line.quantity_ordered - po_line.quantity_received
        reported_quantity = (
            receipt_line.quantity_accepted
            + receipt_line.quantity_damaged
            + receipt_line.quantity_short
        )
        if reported_quantity > outstanding:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Received quantity exceeds outstanding order quantity",
            )

    items = {
        (item.product_id, item.variant_id): item
        for item in product_stock_items(db, {line.product_id for line in po_lines})
    }
    for receipt_line in body.lines:
        po_line = po_lines_by_id[receipt_line.po_line_id]
        item = items.get((po_line.product_id, po_line.variant_id))
        if item is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Product or variant not found.")
        if receipt_line.quantity_accepted and item.tracking_mode == "batch":
            if not receipt_line.batch_number:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "Batch number is required for batch-tracked items.",
                )
        elif receipt_line.batch_number:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Batch number is only valid for batch-tracked items.",
            )
        if item.tracking_mode == "serial":
            if len(receipt_line.serial_numbers) != receipt_line.quantity_accepted:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "Provide one serial number for each accepted unit.",
                )
            if len(receipt_line.damaged_serial_numbers) != receipt_line.quantity_damaged:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "Provide one serial number for each damaged unit.",
                )
        elif receipt_line.serial_numbers or receipt_line.damaged_serial_numbers:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Serial numbers are only valid for serial-tracked items.",
            )

    previous_status = order.status
    try:
        with db.begin_nested():
            receipt = PurchaseOrderReceipt(
                purchase_order_id=order.id,
                received_by=user.id,
                notes=body.notes.strip() if body.notes and body.notes.strip() else None,
            )
            db.add(receipt)
            db.flush()
            receipt_audit_lines = []

            for input_line in body.lines:
                po_line = po_lines_by_id[input_line.po_line_id]
                item = items[(po_line.product_id, po_line.variant_id)]
                unit_price = (
                    input_line.unit_price
                    if input_line.unit_price is not None
                    else po_line.unit_price
                )
                receipt_line = PurchaseOrderReceiptLine(
                    receipt_id=receipt.id,
                    po_line_id=po_line.id,
                    quantity_accepted=input_line.quantity_accepted,
                    quantity_damaged=input_line.quantity_damaged,
                    quantity_short=input_line.quantity_short,
                    unit_price=unit_price,
                    discrepancy_note=input_line.discrepancy_note,
                )
                db.add(receipt_line)
                db.flush()
                po_line.quantity_received += (
                    input_line.quantity_accepted + input_line.quantity_damaged
                )
                if input_line.quantity_accepted + input_line.quantity_damaged:
                    db.add(
                        SupplierPriceHistory(
                            supplier_id=order.supplier_id,
                            product_id=po_line.product_id,
                            variant_id=po_line.variant_id,
                            unit_price=unit_price,
                            receipt_line_id=receipt_line.id,
                        )
                    )

                if item.tracking_mode == "batch" and input_line.quantity_accepted:
                    receive_batch_stock(
                        db,
                        product_id=po_line.product_id,
                        variant_id=po_line.variant_id,
                        location_id=order.location_id,
                        batch_number=input_line.batch_number or "",
                        quantity=input_line.quantity_accepted,
                        user_id=user.id,
                        username=user.username,
                        reference_type="po_receipt_line",
                        reference_id=receipt_line.id,
                    )
                elif item.tracking_mode == "serial" and (
                    input_line.quantity_accepted or input_line.quantity_damaged
                ):
                    serial_ids = receive_serial_stock(
                        db,
                        product_id=po_line.product_id,
                        variant_id=po_line.variant_id,
                        location_id=order.location_id,
                        serial_numbers=input_line.serial_numbers,
                        damaged_serial_numbers=input_line.damaged_serial_numbers,
                        user_id=user.id,
                        username=user.username,
                        reference_type="po_receipt_line",
                        reference_id=receipt_line.id,
                    )
                    db.add_all(
                        PurchaseOrderReceiptSerial(
                            receipt_line_id=receipt_line.id,
                            serial_number_id=serial_id,
                        )
                        for serial_id in serial_ids
                    )
                elif item.tracking_mode == "untracked" and input_line.quantity_accepted:
                    update_stock(
                        db,
                        product_id=po_line.product_id,
                        variant_id=po_line.variant_id,
                        location_id=order.location_id,
                        quantity_delta=input_line.quantity_accepted,
                        movement_type="receipt",
                        user_id=user.id,
                        username=user.username,
                        reference_type="po_receipt_line",
                        reference_id=receipt_line.id,
                    )

                if input_line.quantity_accepted:
                    update_average_unit_cost(
                        db,
                        product_id=po_line.product_id,
                        variant_id=po_line.variant_id,
                        quantity=input_line.quantity_accepted,
                        unit_price=unit_price,
                    )
                receipt_audit_lines.append(
                    {
                        "po_line_id": po_line.id,
                        "quantity_accepted": input_line.quantity_accepted,
                        "quantity_damaged": input_line.quantity_damaged,
                        "quantity_short": input_line.quantity_short,
                        "unit_price": str(unit_price),
                        "discrepancy_note": input_line.discrepancy_note,
                    }
                )

            db.flush()
            _record_order_change(
                db,
                order,
                user,
                "purchase_order_receipt_recorded",
                {"status": previous_status},
                {"receipt_id": receipt.id, "lines": receipt_audit_lines},
            )
            update_purchase_order_receipt_status(
                db,
                purchase_order_id=order.id,
                actor_id=user.id,
                actor_username=user.username,
            )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except InsufficientStockError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    _commit(db)
    db.refresh(order)
    return _out(db, order)


@router.patch("/{order_id}", response_model=PurchaseOrderOut)
def update_purchase_order(
    order_id: int,
    body: PurchaseOrderUpdate,
    db: DbSession,
    user: Annotated[CurrentUser, Depends(require(Permission.PURCHASE_ORDERS_MANAGE))],
) -> PurchaseOrderOut:
    order = _order_or_404(db, order_id, lock=True)
    if _receipt_started(db, order):
        raise HTTPException(status.HTTP_409_CONFLICT, "Cannot modify PO after receipt has started")
    if order.status != "draft":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only draft purchase orders can be modified.")
    values = body.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Provide at least one field.")
    for field in ("supplier_id", "location_id", "expected_delivery_date", "lines"):
        if field in values and values[field] is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Purchase order {field} cannot be null.",
            )
    supplier_id = values.get("supplier_id", order.supplier_id)
    location_id = values.get("location_id", order.location_id)
    supplier = _ensure_active_supplier(db, supplier_id)
    _validate_location(db, location_id)
    existing_lines = db.scalars(
        select(PurchaseOrderLine)
        .where(PurchaseOrderLine.purchase_order_id == order.id)
        .order_by(PurchaseOrderLine.id)
    ).all()
    final_lines = body.lines if "lines" in values else None
    if final_lines is None:
        final_lines = [
            PurchaseOrderLineInput(
                product_id=line.product_id,
                variant_id=line.variant_id,
                quantity_ordered=line.quantity_ordered,
                unit_price=line.unit_price,
            )
            for line in existing_lines
        ]
    _validate_catalog_lines(db, supplier.id, final_lines)

    before = {
        "supplier_id": order.supplier_id,
        "location_id": order.location_id,
        "expected_delivery_date": (
            order.expected_delivery_date.isoformat() if order.expected_delivery_date else None
        ),
        "notes": order.notes,
        "lines": [
            {
                "product_id": line.product_id,
                "variant_id": line.variant_id,
                "quantity_ordered": line.quantity_ordered,
                "unit_price": str(line.unit_price),
            }
            for line in existing_lines
        ],
    }
    order.supplier_id = supplier.id
    order.location_id = location_id
    if "expected_delivery_date" in values:
        order.expected_delivery_date = values["expected_delivery_date"]
    if "notes" in values:
        order.notes = values["notes"].strip() if values["notes"] else None
    if "lines" in values:
        for line in existing_lines:
            db.delete(line)
        db.flush()
        for line in final_lines:
            db.add(
                PurchaseOrderLine(
                    purchase_order_id=order.id,
                    product_id=line.product_id,
                    variant_id=line.variant_id,
                    quantity_ordered=line.quantity_ordered,
                    unit_price=line.unit_price,
                )
            )
    db.flush()
    _record_order_change(
        db,
        order,
        user,
        "purchase_order_updated",
        before,
        {
            "supplier_id": order.supplier_id,
            "location_id": order.location_id,
            "expected_delivery_date": (
                order.expected_delivery_date.isoformat() if order.expected_delivery_date else None
            ),
            "notes": order.notes,
            "lines": [
                {
                    "product_id": line.product_id,
                    "variant_id": line.variant_id,
                    "quantity_ordered": line.quantity_ordered,
                    "unit_price": str(line.unit_price),
                }
                for line in final_lines
            ],
        },
    )
    _commit(db)
    db.refresh(order)
    return _out(db, order)


@router.post("/{order_id}/submit", response_model=PurchaseOrderOut)
def submit_purchase_order(
    order_id: int,
    db: DbSession,
    user: Annotated[CurrentUser, Depends(require(Permission.PURCHASE_ORDERS_MANAGE))],
) -> PurchaseOrderOut:
    order = _order_or_404(db, order_id, lock=True)
    if order.status != "draft":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Only draft purchase orders can be submitted."
        )
    if not db.scalar(
        select(PurchaseOrderLine.id).where(PurchaseOrderLine.purchase_order_id == order.id).limit(1)
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Purchase order requires at least one line."
        )
    previous_status = order.status
    order.status = "submitted"
    order.submitted_at = datetime.now(UTC)
    _record_status_change(db, order, user, previous_status)
    _commit(db)
    db.refresh(order)
    return _out(db, order)


@router.post("/{order_id}/cancel", response_model=PurchaseOrderOut)
def cancel_purchase_order(
    order_id: int,
    db: DbSession,
    user: Annotated[CurrentUser, Depends(require(Permission.PURCHASE_ORDERS_MANAGE))],
) -> PurchaseOrderOut:
    order = _order_or_404(db, order_id, lock=True)
    if order.status not in {"draft", "submitted"}:
        raise HTTPException(status.HTTP_409_CONFLICT, "Purchase order cannot be cancelled.")
    if _receipt_started(db, order):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Cannot cancel purchase order after receipt has started."
        )
    previous_status = order.status
    order.status = "cancelled"
    _record_status_change(db, order, user, previous_status)
    _commit(db)
    db.refresh(order)
    return _out(db, order)
