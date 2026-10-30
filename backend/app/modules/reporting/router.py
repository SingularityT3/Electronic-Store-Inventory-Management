"""HTTP routes for the `reporting` module."""

from collections.abc import Callable
from datetime import UTC, datetime
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
    valuation_rows,
    valuation_table,
)
from app.modules.stock import location_exists

router = APIRouter(prefix="/reporting", tags=["reporting"])


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


ExportFormat = Literal["csv", "pdf"]


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
