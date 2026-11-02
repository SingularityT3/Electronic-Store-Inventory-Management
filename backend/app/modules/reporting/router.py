"""HTTP routes for the `reporting` module."""

from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_session
from app.modules.auth import Permission, require
from app.modules.reporting._internal.export import (
    CSV_MEDIA_TYPE,
    PDF_MEDIA_TYPE,
    ReportTable,
    csv_chunks,
    export_filename,
    pdf_bytes,
)
from app.modules.reporting.service import (
    reorder_rows,
    reorder_table,
    sales_trend_rows,
    sales_trend_table,
    supplier_performance_rows,
    valuation_rows,
    valuation_table,
)
from app.modules.stock import location_exists, location_name

router = APIRouter(prefix="/reporting", tags=["reporting"])
ExportFormat = Literal["csv", "pdf"]


class ValuationItemOut(BaseModel):
    product_id: int
    product_name: str
    sku: str
    variant_id: int | None
    variant_sku: str | None
    variant_attributes: dict[str, object] | None
    location_id: int
    location_name: str
    quantity: int
    unit_cost: Decimal
    value: Decimal
    cost_not_set: bool


class ValuationOut(BaseModel):
    items: list[ValuationItemOut]
    total_value: Decimal


class ReorderItemOut(BaseModel):
    product_id: int
    product_name: str
    sku: str
    variant_id: int | None
    variant_sku: str | None
    variant_attributes: dict[str, object] | None
    location_id: int
    location_name: str
    quantity: int
    reorder_threshold: int
    reorder_to_level: int
    suggested_quantity: int


class SalesTrendItemOut(BaseModel):
    rank: int
    product_id: int
    sku: str
    name: str
    brand: str
    category_name: str
    units_sold: int
    units_returned: int
    net_units: int
    gross_amount: Decimal
    refunded_amount: Decimal
    net_amount: Decimal
    current_stock: int
    inactive: bool


class SalesTrendOut(BaseModel):
    date_from: date
    date_to: date
    location_id: int | None
    location_name: str
    totals: dict[str, int | Decimal]
    best: list[SalesTrendItemOut]
    worst: list[SalesTrendItemOut]


class SupplierPricePointOut(BaseModel):
    recorded_at: datetime
    unit_price: Decimal


class SupplierProductPriceTrendOut(BaseModel):
    product_id: int
    product_name: str
    sku: str
    variant_id: int | None
    price_points: list[SupplierPricePointOut]
    first_price: Decimal
    latest_price: Decimal
    variance: Decimal | None
    variance_percent: Decimal | None


class SupplierPerformanceItemOut(BaseModel):
    supplier_id: int
    supplier_name: str
    purchase_order_count: int
    total_order_value: Decimal
    on_time_delivery_rate: Decimal | None
    on_time_delivery_count: int
    eligible_delivery_count: int
    fulfilment_accuracy: Decimal | None
    quantity_ordered: int
    quantity_accepted: int
    price_trends: list[SupplierProductPriceTrendOut]


class SupplierPerformanceOut(BaseModel):
    date_from: date
    date_to: date
    suppliers: list[SupplierPerformanceItemOut]


def _report_period(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    if date_from > date_to:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "date_from must be on or before date_to."
        )
    today = datetime.now(UTC).date()
    if date_to > today:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Report dates cannot be in the future."
        )
    try:
        ten_years_later = date_from.replace(year=date_from.year + 10)
    except ValueError:
        ten_years_later = date_from.replace(year=date_from.year + 10, day=28)
    if date_to > ten_years_later:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "The report range cannot exceed 10 years."
        )
    start = datetime.combine(date_from, time.min, tzinfo=UTC)
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC)
    return start, end


def _sales_trend(
    db: Session, *, date_from: date, date_to: date, location_id: int | None, limit: int
) -> SalesTrendOut:
    if location_id is not None and not location_exists(db, location_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found.")
    start, end = _report_period(date_from, date_to)
    report = sales_trend_rows(db, start=start, end=end, location_id=location_id)
    rows = report.rows
    return SalesTrendOut(
        date_from=date_from,
        date_to=date_to,
        location_id=location_id,
        location_name=location_name(db, location_id)
        if location_id is not None
        else "All locations",
        totals={
            "units_sold": report.units_sold,
            "units_returned": report.units_returned,
            "net_units": report.net_units,
            "gross_amount": report.gross_amount,
            "refunded_amount": report.refunded_amount,
            "net_amount": report.net_amount,
            "products_with_sales": report.products_with_sales,
            "products_with_zero_sales": report.products_with_zero_sales,
        },
        best=[SalesTrendItemOut(**row.__dict__) for row in rows[:limit]],
        worst=[
            SalesTrendItemOut(**row.__dict__)
            for row in sorted(rows[-limit:], key=lambda row: (-row.rank, row.name, row.product_id))
        ],
    )


@router.get("/sales-trend", response_model=SalesTrendOut)
def sales_trend_report(
    db: Annotated[Session, Depends(get_session)],
    _: Annotated[object, Depends(require(Permission.REPORTS_VIEW))],
    date_from: date,
    date_to: date,
    location_id: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> SalesTrendOut:
    return _sales_trend(
        db, date_from=date_from, date_to=date_to, location_id=location_id, limit=limit
    )


@router.get(
    "/supplier-performance",
    response_model=SupplierPerformanceOut,
    dependencies=[Depends(require(Permission.REPORTS_VIEW))],
)
def supplier_performance_report(
    db: Annotated[Session, Depends(get_session)],
    date_from: date,
    date_to: date,
    supplier_ids: Annotated[list[int] | None, Query()] = None,
) -> SupplierPerformanceOut:
    if supplier_ids is not None and (
        any(supplier_id < 1 for supplier_id in supplier_ids)
        or len(supplier_ids) != len(set(supplier_ids))
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Supplier IDs must be positive and unique.",
        )
    start, end = _report_period(date_from, date_to)
    reports = supplier_performance_rows(db, start=start, end=end, supplier_ids=supplier_ids)
    if supplier_ids is not None and len(reports) != len(supplier_ids):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Supplier not found.")
    return SupplierPerformanceOut(
        date_from=date_from,
        date_to=date_to,
        suppliers=[
            SupplierPerformanceItemOut(
                supplier_id=report.supplier_id,
                supplier_name=report.supplier_name,
                purchase_order_count=report.purchase_order_count,
                total_order_value=report.total_order_value,
                on_time_delivery_rate=report.on_time_delivery_rate,
                on_time_delivery_count=report.on_time_delivery_count,
                eligible_delivery_count=report.eligible_delivery_count,
                fulfilment_accuracy=report.fulfilment_accuracy,
                quantity_ordered=report.quantity_ordered,
                quantity_accepted=report.quantity_accepted,
                price_trends=[
                    SupplierProductPriceTrendOut(
                        product_id=trend.product_id,
                        product_name=trend.product_name,
                        sku=trend.sku,
                        variant_id=trend.variant_id,
                        price_points=[
                            SupplierPricePointOut(
                                recorded_at=point.recorded_at,
                                unit_price=point.unit_price,
                            )
                            for point in trend.price_points
                        ],
                        first_price=trend.first_price,
                        latest_price=trend.latest_price,
                        variance=trend.variance,
                        variance_percent=trend.variance_percent,
                    )
                    for trend in report.price_trends
                ],
            )
            for report in reports
        ],
    )


@router.get("/sales-trend/export", dependencies=[Depends(require(Permission.REPORTS_VIEW))])
def export_sales_trend(
    db: Annotated[Session, Depends(get_session)],
    export_format: Annotated[ExportFormat, Query(alias="format")],
    date_from: date,
    date_to: date,
    location_id: Annotated[int | None, Query(ge=1)] = None,
) -> Response:
    if location_id is not None and not location_exists(db, location_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found.")
    start, end = _report_period(date_from, date_to)
    table = sales_trend_table(db, start=start, end=end, location_id=location_id)
    generated_at = datetime.now(UTC)
    headers = {
        "Content-Disposition": (
            f'attachment; filename="{export_filename(table.title, generated_at, export_format)}"'
        ),
        "Cache-Control": "no-store",
    }
    if export_format == "csv":
        return StreamingResponse(csv_chunks(table), media_type=CSV_MEDIA_TYPE, headers=headers)
    return Response(pdf_bytes(table, generated_at), media_type=PDF_MEDIA_TYPE, headers=headers)


@router.get(
    "/valuation",
    response_model=ValuationOut,
    dependencies=[Depends(require(Permission.REPORTS_VIEW))],
)
def stock_valuation(
    db: Annotated[Session, Depends(get_session)],
    location_id: Annotated[int | None, Query(ge=1)] = None,
) -> ValuationOut:
    if location_id is not None and not location_exists(db, location_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found.")

    rows, total = valuation_rows(db, location_id=location_id)
    items = []
    for row in rows:
        position = row.position
        items.append(
            ValuationItemOut(
                product_id=position.product_id,
                product_name=position.product_name,
                sku=position.sku,
                variant_id=position.variant_id,
                variant_sku=position.variant_sku,
                variant_attributes=position.variant_attributes,
                location_id=position.location_id,
                location_name=position.location_name,
                quantity=position.quantity,
                unit_cost=row.unit_cost,
                value=row.value,
                cost_not_set=row.cost_not_set,
            )
        )
    return ValuationOut(items=items, total_value=total)


@router.get(
    "/reorder",
    response_model=list[ReorderItemOut],
    dependencies=[Depends(require(Permission.REPORTS_VIEW))],
)
def reorder_report(
    db: Annotated[Session, Depends(get_session)],
    location_id: Annotated[int | None, Query(ge=1)] = None,
) -> list[ReorderItemOut]:
    if location_id is not None and not location_exists(db, location_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found.")

    return [
        ReorderItemOut(
            product_id=position.product_id,
            product_name=position.product_name,
            sku=position.sku,
            variant_id=position.variant_id,
            variant_sku=position.variant_sku,
            variant_attributes=position.variant_attributes,
            location_id=position.location_id,
            location_name=position.location_name,
            quantity=position.quantity,
            reorder_threshold=position.reorder_threshold,
            reorder_to_level=position.reorder_to_level,
            suggested_quantity=suggested_quantity,
        )
        for position, suggested_quantity in reorder_rows(db, location_id=location_id)
    ]


def _export(
    db: Session,
    build: Callable[..., ReportTable],
    location_id: int | None,
    export_format: ExportFormat,
) -> Response:
    if location_id is not None and not location_exists(db, location_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found.")
    table = build(db, location_id=location_id)
    generated_at = datetime.now(UTC)
    headers = {
        "Content-Disposition": (
            f'attachment; filename="{export_filename(table.title, generated_at, export_format)}"'
        ),
        "Cache-Control": "no-store",
    }
    if export_format == "csv":
        return StreamingResponse(csv_chunks(table), media_type=CSV_MEDIA_TYPE, headers=headers)
    return Response(pdf_bytes(table, generated_at), media_type=PDF_MEDIA_TYPE, headers=headers)


@router.get("/valuation/export", dependencies=[Depends(require(Permission.REPORTS_VIEW))])
def export_stock_valuation(
    db: Annotated[Session, Depends(get_session)],
    export_format: Annotated[ExportFormat, Query(alias="format")],
    location_id: Annotated[int | None, Query(ge=1)] = None,
) -> Response:
    return _export(db, valuation_table, location_id, export_format)


@router.get("/reorder/export", dependencies=[Depends(require(Permission.REPORTS_VIEW))])
def export_reorder_report(
    db: Annotated[Session, Depends(get_session)],
    export_format: Annotated[ExportFormat, Query(alias="format")],
    location_id: Annotated[int | None, Query(ge=1)] = None,
) -> Response:
    return _export(db, reorder_table, location_id, export_format)
