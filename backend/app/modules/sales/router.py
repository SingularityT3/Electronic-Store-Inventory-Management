"""HTTP routes for recording sales and reading receipt data."""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import String, case, cast, func, or_, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_session
from app.modules.audit import audit_service
from app.modules.auth import (
    CurrentUser,
    ManagerApprovalError,
    Permission,
    authorize_location,
    require,
    user_full_names,
)
from app.modules.sales._internal.models import (
    Invoice,
    Payment,
    Return,
    ReturnLine,
    ReturnLineBatch,
    Sale,
    SaleLine,
    SaleLineBatch,
    SaleLineSerial,
)
from app.modules.sales.documents import Document, document_pdf
from app.modules.sales.service import (
    InvoiceNotFoundError,
    PaymentInput,
    ReturnLateApprovalRequiredError,
    ReturnLineInput,
    SaleInputError,
    SaleLineInput,
    SaleStockError,
    SaleTrackingError,
    get_credit_note,
    get_sale_return_status,
    invoice_label,
    lookup_sale_by_invoice,
    parse_invoice_number,
    process_return,
    record_sale,
)
from app.modules.stock import (
    batch_stock_positions,
    location_details_many,
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
    invoice_label: str = ""
    issued_at: datetime
    total: Decimal
    content: dict[str, object] = Field(default_factory=dict)


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
    return_status: Literal["none", "partially_returned", "fully_returned"] = "none"


class SaleLookupLineOut(BaseModel):
    id: int
    product_id: int
    product_name: str
    sku: str
    variant_id: int | None
    variant_sku: str | None
    variant_attributes: dict[str, object] | None
    quantity: int
    unit_price: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    line_total: Decimal
    serial_numbers: list[str] = Field(default_factory=list)
    quantity_returned: int
    quantity_returnable: int
    returnable_serials: list[str] = Field(default_factory=list)
    returnable_serial_ids: list[int] = Field(default_factory=list)


class SaleLookupOut(BaseModel):
    id: int
    location_id: int
    location_name: str
    cashier_id: int
    sold_at: datetime
    subtotal: Decimal
    discount_total: Decimal
    tax_total: Decimal
    total: Decimal
    customer_name: str | None
    lines: list[SaleLookupLineOut]
    payments: list[PaymentOut]
    invoice: InvoiceOut
    return_status: Literal["none", "partially_returned", "fully_returned"]
    days_since_sale: int
    return_window_days: int
    requires_manager_approval: bool


class ReturnLineIn(BaseModel):
    sale_line_id: int = Field(ge=1)
    quantity: int = Field(ge=1)
    condition: Literal["resaleable", "damaged"] = "resaleable"
    serial_number_ids: list[int] | None = None


class ManagerApprovalIn(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class ReturnIn(BaseModel):
    invoice_number: str | int
    lines: list[ReturnLineIn]
    reason: str = Field(min_length=1, max_length=500)
    manager_approval: ManagerApprovalIn | None = None


class ReturnCreditNoteLineOut(BaseModel):
    id: int
    sale_line_id: int
    product_id: int
    product_name: str
    sku: str
    variant_id: int | None
    variant_sku: str | None
    quantity: int
    condition: str
    restocked: bool
    refund_amount: Decimal
    serial_numbers: list[str] = Field(default_factory=list)


class ReturnCreditNoteOut(BaseModel):
    credit_note_number: str
    return_id: int
    sale_id: int
    invoice_number: int
    created_at: datetime
    sold_at: datetime
    location_id: int
    location_name: str
    reason: str
    processor_username: str
    approver_username: str | None
    refund_total: Decimal
    non_sellable_quantity: int
    lines: list[ReturnCreditNoteLineOut]
    content: dict[str, object] = Field(default_factory=dict)


class SalesHistoryItemOut(BaseModel):
    sale_id: int
    invoice_number: int
    invoice_label: str
    sold_at: datetime
    cashier_name: str
    location_id: int
    location_name: str
    total: Decimal
    return_status: Literal["none", "partially_returned", "fully_returned"]


class SalesHistoryOut(BaseModel):
    items: list[SalesHistoryItemOut]
    total: int
    page: int
    page_size: int


class CreditNoteSummaryOut(BaseModel):
    credit_note_number: str
    return_id: int
    created_at: datetime
    refund_total: Decimal


class InvoiceDocumentOut(BaseModel):
    content: dict[str, object]
    return_status: Literal["none", "partially_returned", "fully_returned"]
    credit_notes: list[CreditNoteSummaryOut]


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
            invoice_label=invoice_label(invoice.invoice_number),
            issued_at=invoice.issued_at,
            total=invoice.total,
            content=invoice.content,
        ),
        return_status=get_sale_return_status(db, sale.id),
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


@router.get("/by-invoice", include_in_schema=False)
@router.get("/by-invoice/", include_in_schema=False)
def get_sale_by_invoice_empty(
    user: Annotated[CurrentUser, Depends(require(Permission.SALES_RECORD))],
) -> None:
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")


@router.get("/by-invoice/{invoice_number}", response_model=SaleLookupOut)
def get_sale_by_invoice(
    invoice_number: str,
    db: Annotated[Session, Depends(get_session)],
    user: Annotated[CurrentUser, Depends(require(Permission.SALES_RECORD))],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SaleLookupOut:
    try:
        data = lookup_sale_by_invoice(db, invoice_number_raw=invoice_number, settings=settings)
    except InvoiceNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found") from None

    authorize_location(db, user, data.sale.location_id, "Read sale")

    return SaleLookupOut(
        id=data.sale.id,
        location_id=data.sale.location_id,
        location_name=data.location_name,
        cashier_id=data.sale.cashier_id,
        sold_at=data.sale.sold_at,
        subtotal=data.sale.subtotal,
        discount_total=data.sale.discount_total,
        tax_total=data.sale.tax_total,
        total=data.sale.total,
        customer_name=data.sale.customer_name,
        lines=[
            SaleLookupLineOut(
                id=line.id,
                product_id=line.product_id,
                product_name=line.product_name,
                sku=line.sku,
                variant_id=line.variant_id,
                variant_sku=line.variant_sku,
                variant_attributes=line.variant_attributes,
                quantity=line.quantity,
                unit_price=line.unit_price,
                discount_amount=line.discount_amount,
                tax_amount=line.tax_amount,
                line_total=line.line_total,
                serial_numbers=line.serial_numbers,
                quantity_returned=line.quantity_returned,
                quantity_returnable=line.quantity_returnable,
                returnable_serials=line.returnable_serials,
                returnable_serial_ids=line.returnable_serial_ids,
            )
            for line in data.lines
        ],
        payments=[PaymentOut.model_validate(p, from_attributes=True) for p in data.payments],
        invoice=InvoiceOut(
            invoice_number=data.invoice.invoice_number,
            invoice_label=invoice_label(data.invoice.invoice_number),
            issued_at=data.invoice.issued_at,
            total=data.invoice.total,
            content=data.invoice.content,
        ),
        return_status=data.return_status,
        days_since_sale=data.days_since_sale,
        return_window_days=data.return_window_days,
        requires_manager_approval=data.requires_manager_approval,
    )


@router.post("/returns", response_model=ReturnCreditNoteOut, status_code=status.HTTP_201_CREATED)
def create_return(
    body: ReturnIn,
    db: Annotated[Session, Depends(get_session)],
    user: Annotated[CurrentUser, Depends(require(Permission.SALES_RECORD))],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReturnCreditNoteOut:
    inv_num = parse_invoice_number(body.invoice_number)
    if inv_num is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    invoice = db.scalar(select(Invoice).where(Invoice.invoice_number == inv_num))
    if invoice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    sale = db.scalar(select(Sale).where(Sale.id == invoice.sale_id))
    if sale is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    authorize_location(db, user, sale.location_id, "Process return")

    approval_tuple = (
        (body.manager_approval.username, body.manager_approval.password)
        if body.manager_approval
        else None
    )
    line_inputs = [
        ReturnLineInput(
            sale_line_id=line.sale_line_id,
            quantity=line.quantity,
            condition=line.condition,
            serial_number_ids=tuple(line.serial_number_ids or ()),
        )
        for line in body.lines
    ]

    try:
        credit_note = process_return(
            db,
            invoice_number_raw=body.invoice_number,
            lines=line_inputs,
            reason=body.reason,
            processor_id=user.id,
            processor_username=user.username,
            processor_role=user.role,
            manager_approval=approval_tuple,
            settings=settings,
        )
        db.commit()
        return ReturnCreditNoteOut.model_validate(credit_note, from_attributes=True)
    except InvoiceNotFoundError:
        db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found") from None
    except ReturnLateApprovalRequiredError:
        db.rollback()
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            {
                "code": "manager_approval_required",
                "message": "Manager approval is required for sales older than 30 days.",
            },
        ) from None
    except ManagerApprovalError:
        db.rollback()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Manager approval failed.") from None
    except SaleInputError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, exc.errors) from None
    except SaleTrackingError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None
    except Exception:
        db.rollback()
        raise


@router.get("/returns/{return_id}", response_model=ReturnCreditNoteOut)
def get_return(
    return_id: int,
    db: Annotated[Session, Depends(get_session)],
    user: Annotated[CurrentUser, Depends(require(Permission.SALES_RECORD))],
) -> ReturnCreditNoteOut:
    credit_note = get_credit_note(db, return_id)
    authorize_location(db, user, credit_note.location_id, "Read credit note")
    return ReturnCreditNoteOut.model_validate(credit_note, from_attributes=True)


@router.get("/history", response_model=SalesHistoryOut)
def sales_history(
    db: Annotated[Session, Depends(get_session)],
    user: Annotated[CurrentUser, Depends(require(Permission.SALES_RECORD))],
    invoice: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    location_id: Annotated[int | None, Query(ge=1)] = None,
    return_status: Literal["none", "partially_returned", "fully_returned"] | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> SalesHistoryOut:
    returned_qty = (
        select(func.coalesce(func.sum(ReturnLine.quantity), 0))
        .join(SaleLine, SaleLine.id == ReturnLine.sale_line_id)
        .where(SaleLine.sale_id == Sale.id)
        .correlate(Sale)
        .scalar_subquery()
    )
    sold_qty = (
        select(func.coalesce(func.sum(SaleLine.quantity), 0))
        .where(SaleLine.sale_id == Sale.id)
        .correlate(Sale)
        .scalar_subquery()
    )
    status_expr = case(
        (returned_qty == 0, "none"),
        (returned_qty >= sold_qty, "fully_returned"),
        else_="partially_returned",
    )
    query = select(Sale, Invoice.invoice_number, status_expr, func.count().over()).join(
        Invoice, Invoice.sale_id == Sale.id
    )
    if not user.sees_all_locations:
        if user.location_id is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "A location assignment is required.")
        query = query.where(Sale.location_id == user.location_id)
    else:
        if location_id is not None:
            query = query.where(Sale.location_id == location_id)
    if invoice:
        search = invoice.strip().upper()
        if search.startswith("INV-"):
            search = search[4:].strip()
        if search:
            raw_number = cast(Invoice.invoice_number, String)
            padded_number = func.lpad(raw_number, 4, "0")
            pattern = f"%{search}%"
            query = query.where(or_(raw_number.ilike(pattern), padded_number.ilike(pattern)))
    if date_from:
        query = query.where(Sale.sold_at >= datetime.combine(date_from, time.min, tzinfo=UTC))
    if date_to:
        query = query.where(
            Sale.sold_at < datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC)
        )
    if return_status:
        query = query.where(status_expr == return_status)
    rows = db.execute(
        query.order_by(Sale.sold_at.desc(), Sale.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    sale_ids = [row[0].cashier_id for row in rows]
    location_ids = [row[0].location_id for row in rows]
    cashier_names = user_full_names(db, sale_ids)
    location_names = location_details_many(db, location_ids)
    total = int(rows[0][3]) if rows else 0
    return SalesHistoryOut(
        items=[
            SalesHistoryItemOut(
                sale_id=sale.id,
                invoice_number=number,
                invoice_label=invoice_label(number),
                sold_at=sale.sold_at,
                cashier_name=cashier_names.get(sale.cashier_id, f"User {sale.cashier_id}"),
                location_id=sale.location_id,
                location_name=(
                    location_names.get(sale.location_id) or (f"Location {sale.location_id}", None)
                )[0],
                total=sale.total,
                return_status=state,
            )
            for sale, number, state, _ in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/invoices/{invoice_number}", response_model=InvoiceDocumentOut)
def get_invoice_document(
    invoice_number: str,
    db: Annotated[Session, Depends(get_session)],
    user: Annotated[CurrentUser, Depends(require(Permission.SALES_RECORD))],
) -> InvoiceDocumentOut:
    number = parse_invoice_number(invoice_number)
    inv = db.scalar(select(Invoice).where(Invoice.invoice_number == number)) if number else None
    if inv is None or not inv.content or not inv.content.get("lines"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    sale = db.get(Sale, inv.sale_id)
    if sale is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    authorize_location(db, user, sale.location_id, "Read invoice")
    state = get_sale_return_status(db, sale.id)
    notes = db.execute(
        select(Return, Return.content)
        .where(Return.sale_id == sale.id)
        .order_by(Return.created_at, Return.id)
    ).all()
    return InvoiceDocumentOut(
        content=inv.content,
        return_status=state,
        credit_notes=[
            CreditNoteSummaryOut(
                credit_note_number=ret.content.get("credit_note_number", f"CN-{ret.id:04d}"),
                return_id=ret.id,
                created_at=ret.created_at,
                refund_total=ret.refund_total,
            )
            for ret, _ in notes
        ],
    )


def _pdf_response(
    db: Session, user: CurrentUser, document: Document, filename: str, action: str, entity_id: str
) -> Response:
    try:
        content = document_pdf(document)
    except Exception:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Could not generate the PDF. You can try again or view the invoice on screen.",
        ) from None
    audit_service.record(
        db,
        module="sales",
        action=action,
        user_id=user.id,
        username=user.username,
        entity_type="invoice" if action == "invoice_pdf_exported" else "credit_note",
        entity_id=entity_id,
        details=f"Exported {filename}.",
    )
    db.commit()
    return Response(
        content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/invoices/{invoice_number}/pdf")
def get_invoice_pdf(
    invoice_number: str,
    db: Annotated[Session, Depends(get_session)],
    user: Annotated[CurrentUser, Depends(require(Permission.SALES_RECORD))],
) -> Response:
    number = parse_invoice_number(invoice_number)
    inv = db.scalar(select(Invoice).where(Invoice.invoice_number == number)) if number else None
    if inv is None or not inv.content or not inv.content.get("lines"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    sale = db.get(Sale, inv.sale_id)
    if sale is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    authorize_location(db, user, sale.location_id, "Export invoice")
    state = get_sale_return_status(db, sale.id)
    annotation = {
        "partially_returned": "Partially Returned",
        "fully_returned": "Fully Returned",
    }.get(state)
    label = invoice_label(inv.invoice_number)
    return _pdf_response(
        db,
        user,
        Document("invoice", inv.content, annotation),
        f"invoice-{label}.pdf",
        "invoice_pdf_exported",
        str(inv.id),
    )


@router.get("/returns/{return_id}/pdf")
def get_credit_note_pdf(
    return_id: int,
    db: Annotated[Session, Depends(get_session)],
    user: Annotated[CurrentUser, Depends(require(Permission.SALES_RECORD))],
) -> Response:
    note = get_credit_note(db, return_id)
    authorize_location(db, user, note.location_id, "Export credit note")
    filename = f"credit-note-{note.credit_note_number}.pdf"
    return _pdf_response(
        db,
        user,
        Document("credit_note", note.content),
        filename,
        "credit_note_pdf_exported",
        str(return_id),
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
