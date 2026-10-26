"""HTTP routes for recording sales and reading receipt data."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_session
from app.modules.auth import CurrentUser, Permission, authorize_location, require
from app.modules.sales._internal.models import (
    Invoice,
    Payment,
    ReturnLineBatch,
    Sale,
    SaleLine,
    SaleLineBatch,
    SaleLineSerial,
)
from app.modules.sales.service import (
    PaymentInput,
    SaleInputError,
    SaleLineInput,
    SaleStockError,
    record_sale,
)
from app.modules.stock import (
    batch_stock_positions,
    location_exists,
    serial_number_labels,
    stock_positions,
)

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


class SaleLineIn(BaseModel):
    product_id: int = Field(ge=1)
    variant_id: int | None = Field(default=None, ge=1)
    quantity: int = Field(ge=1, le=100_000)
    discount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    discount_type: Literal["percentage", "amount"] = "amount"
    serial_numbers: list[Annotated[str, Field(max_length=100)]] = Field(default_factory=list)


class PaymentIn(BaseModel):
    method: str
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    reference: str | None = Field(default=None, max_length=100)


class SaleIn(BaseModel):
    location_id: int | None = Field(default=None, ge=1)
    lines: list[SaleLineIn]
    payments: list[PaymentIn]
    customer_name: str | None = Field(default=None, max_length=200)
    idempotency_key: str | None = Field(default=None, max_length=100)


class SaleLineOut(BaseModel):
    id: int
    product_id: int
    variant_id: int | None
    quantity: int
    unit_price: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    line_total: Decimal
    serial_numbers: list[str] = Field(default_factory=list)


class PaymentOut(BaseModel):
    id: int
    method: str
    amount: Decimal
    reference: str | None


class InvoiceOut(BaseModel):
    invoice_number: int
    issued_at: datetime
    total: Decimal


class SaleOut(BaseModel):
    id: int
    location_id: int
    cashier_id: int
    sold_at: datetime
    subtotal: Decimal
    discount_total: Decimal
    tax_total: Decimal
    total: Decimal
    customer_name: str | None
    lines: list[SaleLineOut]
    payments: list[PaymentOut]
    invoice: InvoiceOut


class BatchLocationOut(BaseModel):
    location_id: int
    quantity_in_stock: int


class BatchReceiptOut(BaseModel):
    location_id: int
    reference_type: str
    reference_id: int
    quantity: int


class BatchSoldOut(BaseModel):
    invoice_number: int
    quantity_sold: int
    quantity_returned: int
    quantity_still_sold: int


class BatchRecallOut(BaseModel):
    batch_id: int
    batch_number: str
    product_id: int
    variant_id: int | None
    quantity_received: int
    quantity_in_stock: int
    locations: list[BatchLocationOut]
    receipts: list[BatchReceiptOut]
    sold: list[BatchSoldOut]


def _sale_line_out(db: Session, line: SaleLine) -> SaleLineOut:
    serial_ids = db.scalars(
        select(SaleLineSerial.serial_number_id).where(SaleLineSerial.sale_line_id == line.id)
    ).all()
    labels = serial_number_labels(db, serial_ids)
    return SaleLineOut(
        id=line.id,
        product_id=line.product_id,
        variant_id=line.variant_id,
        quantity=line.quantity,
        unit_price=line.unit_price,
        discount_amount=line.discount_amount,
        tax_amount=line.tax_amount,
        line_total=line.line_total,
        serial_numbers=[labels[serial_id] for serial_id in serial_ids if serial_id in labels],
    )


def _sale_out(db: Session, sale: Sale) -> SaleOut:
    invoice = db.scalar(select(Invoice).where(Invoice.sale_id == sale.id))
    if invoice is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Sale invoice is missing.")
    return SaleOut(
        id=sale.id,
        location_id=sale.location_id,
        cashier_id=sale.cashier_id,
        sold_at=sale.sold_at,
        subtotal=sale.subtotal,
        discount_total=sale.discount_total,
        tax_total=sale.tax_total,
        total=sale.total,
        customer_name=sale.customer_name,
        lines=[
            _sale_line_out(db, line)
            for line in db.scalars(
                select(SaleLine).where(SaleLine.sale_id == sale.id).order_by(SaleLine.id)
            )
        ],
        payments=[
            PaymentOut.model_validate(payment, from_attributes=True)
            for payment in db.scalars(
                select(Payment).where(Payment.sale_id == sale.id).order_by(Payment.id)
            )
        ],
        invoice=InvoiceOut(
            invoice_number=invoice.invoice_number,
            issued_at=invoice.issued_at,
            total=invoice.total,
        ),
    )


@router.get("/availability", response_model=list[AvailabilityOut])
def item_availability(
    db: Annotated[Session, Depends(get_session)],
    user: Annotated[CurrentUser, Depends(require(Permission.SALES_RECORD))],
    location_id: Annotated[int | None, Query(ge=1)] = None,
    ids: Annotated[list[int] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> list[AvailabilityOut]:
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
    positions = stock_positions(db, location_id=location_id, product_ids=ids)
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
        for position in positions[:limit]
    ]


@router.post("", response_model=SaleOut, status_code=status.HTTP_201_CREATED)
def create_sale(
    body: SaleIn,
    db: Annotated[Session, Depends(get_session)],
    user: Annotated[CurrentUser, Depends(require(Permission.SALES_RECORD))],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SaleOut:
    location_id = body.location_id
    if not user.sees_all_locations:
        if location_id is not None:
            authorize_location(db, user, location_id, "Record sale")
        location_id = user.location_id
    elif location_id is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"field": "location_id", "message": "Location is required."},
        )
    if location_id is None or not location_exists(db, location_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found.")
    try:
        sale = record_sale(
            db,
            location_id=location_id,
            cashier_id=user.id,
            cashier_username=user.username,
            lines=[
                SaleLineInput(
                    item.product_id,
                    item.variant_id,
                    item.quantity,
                    item.discount,
                    item.discount_type,
                    tuple(item.serial_numbers),
                )
                for item in body.lines
            ],
            payments=[
                PaymentInput(item.method, item.amount, item.reference) for item in body.payments
            ],
            customer_name=body.customer_name,
            idempotency_key=body.idempotency_key,
            settings=settings,
        )
        db.commit()
        return _sale_out(db, sale)
    except SaleStockError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, exc.errors) from None
    except SaleInputError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, exc.errors) from None
    except Exception:
        db.rollback()
        raise


@router.get("/batches/{batch_id}/recall", response_model=BatchRecallOut)
def batch_recall(
    batch_id: int,
    db: Annotated[Session, Depends(get_session)],
    user: Annotated[CurrentUser, Depends(require(Permission.STOCK_VIEW))],
    location_id: Annotated[int | None, Query(ge=1)] = None,
) -> BatchRecallOut:
    if not user.sees_all_locations:
        if user.location_id is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "A location assignment is required.")
        if location_id is not None:
            authorize_location(db, user, location_id, "View batch recall")
        location_id = user.location_id
    if location_id is not None and not location_exists(db, location_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found.")
    batch_data = batch_stock_positions(db, batch_id=batch_id, location_id=location_id)
    if batch_data is None or (location_id is not None and not batch_data.locations):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Batch not found.")

    stock_ids = [position.batch_stock_id for position in batch_data.locations]
    sold_rows = []
    if stock_ids:
        allocations = db.execute(
            select(SaleLineBatch, Invoice.invoice_number)
            .join(SaleLine, SaleLine.id == SaleLineBatch.sale_line_id)
            .join(Invoice, Invoice.sale_id == SaleLine.sale_id)
            .where(SaleLineBatch.batch_stock_id.in_(stock_ids))
            .order_by(Invoice.invoice_number, SaleLineBatch.id)
        ).all()
        for allocation, invoice_number in allocations:
            returned = db.scalar(
                select(func.coalesce(func.sum(ReturnLineBatch.quantity), 0)).where(
                    ReturnLineBatch.sale_line_batch_id == allocation.id
                )
            )
            quantity_returned = int(returned or 0)
            sold_rows.append(
                BatchSoldOut(
                    invoice_number=invoice_number,
                    quantity_sold=allocation.quantity,
                    quantity_returned=quantity_returned,
                    quantity_still_sold=allocation.quantity - quantity_returned,
                )
            )
    locations = [
        BatchLocationOut(
            location_id=position.location_id,
            quantity_in_stock=position.quantity_on_hand,
        )
        for position in batch_data.locations
    ]
    return BatchRecallOut(
        batch_id=batch_data.batch_id,
        batch_number=batch_data.batch_number,
        product_id=batch_data.product_id,
        variant_id=batch_data.variant_id,
        quantity_received=batch_data.quantity_received,
        quantity_in_stock=sum(item.quantity_in_stock for item in locations),
        locations=locations,
        receipts=[
            BatchReceiptOut(
                location_id=receipt.location_id,
                reference_type=receipt.reference_type,
                reference_id=receipt.reference_id,
                quantity=receipt.quantity,
            )
            for receipt in batch_data.receipts
        ],
        sold=sold_rows,
    )


@router.get("/{sale_id}", response_model=SaleOut)
def get_sale(
    sale_id: int,
    db: Annotated[Session, Depends(get_session)],
    user: Annotated[CurrentUser, Depends(require(Permission.SALES_RECORD))],
) -> SaleOut:
    sale = db.scalar(select(Sale).where(Sale.id == sale_id))
    if sale is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sale not found.")
    authorize_location(db, user, sale.location_id, "Read sale")
    return _sale_out(db, sale)
