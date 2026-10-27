"""HTTP routes for the `purchasing` module."""

import re
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, ValidationInfo, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_session
from app.modules.audit import audit_service
from app.modules.auth import CurrentUser, Permission, require
from app.modules.product import ProductStockItem, product_stock_items
from app.modules.purchasing._internal.models import (
    PurchaseOrder,
    Supplier,
    SupplierPriceHistory,
    SupplierProduct,
)
from app.modules.purchasing.purchase_orders import router as purchase_orders_router

router = APIRouter(prefix="/purchasing", tags=["purchasing"])
DbSession = Annotated[Session, Depends(get_session)]
EMAIL_LOCAL_PATTERN = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+$")
EMAIL_DOMAIN_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
OPEN_ORDER_STATUSES = ("draft", "submitted", "partially_received")


def _clean_supplier_field(value: str | None, field: str | None) -> str | None:
    """Trim a supplier field. A blank name is an error; other blank fields are cleared."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        if field == "name":
            raise ValueError("Supplier name is required.")
        return None
    return value


class SupplierInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    contact_name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=30)
    address: str | None = None

    @field_validator("name", "contact_name", "email", "phone", "address")
    @classmethod
    def strip_strings(cls, value: str | None, info: ValidationInfo) -> str | None:
        return _clean_supplier_field(value, info.field_name)


class SupplierUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    contact_name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=30)
    address: str | None = None

    @field_validator("name", "contact_name", "email", "phone", "address")
    @classmethod
    def strip_strings(cls, value: str | None, info: ValidationInfo) -> str | None:
        return _clean_supplier_field(value, info.field_name)


class SupplierOut(BaseModel):
    id: int
    name: str
    contact_name: str | None
    email: str | None
    phone: str | None
    address: str | None
    is_active: bool


class SupplierProductCreate(BaseModel):
    product_id: int = Field(ge=1)
    variant_id: int | None = Field(default=None, ge=1)
    supplier_sku: str | None = Field(default=None, max_length=64)
    supplier_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)

    @field_validator("supplier_sku")
    @classmethod
    def strip_sku(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class SupplierProductUpdate(BaseModel):
    supplier_sku: str | None = Field(default=None, max_length=64)
    supplier_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)

    @field_validator("supplier_sku")
    @classmethod
    def strip_sku(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class SupplierProductOut(BaseModel):
    id: int
    supplier_id: int
    product_id: int
    variant_id: int | None
    supplier_sku: str | None
    supplier_price: Decimal
    product_name: str
    product_sku: str


class SupplierPriceHistoryOut(BaseModel):
    id: int
    supplier_id: int
    supplier_name: str
    product_id: int
    product_name: str
    variant_id: int | None
    sku: str
    unit_price: Decimal
    recorded_at: datetime
    receipt_line_id: int | None


def _validate_email(email: str | None) -> None:
    if email:
        local, separator, domain = email.partition("@")
        labels = domain.split(".")
        if (
            not separator
            or len(local) > 64
            or len(domain) > 253
            or not EMAIL_LOCAL_PATTERN.fullmatch(local)
            or len(labels) < 2
            or any(not EMAIL_DOMAIN_LABEL_PATTERN.fullmatch(label) for label in labels)
        ):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid email format")


def _supplier_or_404(db: Session, supplier_id: int) -> Supplier:
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Supplier not found.")
    return supplier


def _active_supplier(db: Session, supplier_id: int) -> Supplier:
    supplier = _supplier_or_404(db, supplier_id)
    if not supplier.is_active:
        raise HTTPException(status.HTTP_409_CONFLICT, "Supplier is inactive.")
    return supplier


def _constraint_name(error: IntegrityError) -> str | None:
    return getattr(getattr(error.orig, "diag", None), "constraint_name", None)


def _commit(db: Session, *, duplicate_message: str | None = None) -> None:
    try:
        db.commit()
    except IntegrityError as error:
        constraint = _constraint_name(error)
        db.rollback()
        if duplicate_message and constraint in {
            "uq_suppliers_name",
            "uq_supplier_products_supplier_id_product_id_variant_id",
        }:
            raise HTTPException(status.HTTP_409_CONFLICT, duplicate_message) from None
        raise


def _audit(
    db: Session,
    user: CurrentUser,
    *,
    action: str,
    entity_type: str,
    entity_id: int,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    audit_service.record(
        db,
        module="purchasing",
        action=action,
        user_id=user.id,
        username=user.username,
        entity_type=entity_type,
        entity_id=str(entity_id),
        before=before,
        after=after,
    )


def _product_item(
    db: Session, product_id: int, variant_id: int | None, *, for_new_entry: bool = False
) -> tuple[str, str]:
    """The name and SKU of a catalog item. A new entry needs an item that can be ordered."""
    items = product_stock_items(db, [product_id])
    if not items or (for_new_entry and not any(item.is_active for item in items)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found.")
    item = next((item for item in items if item.variant_id == variant_id), None)
    if variant_id is not None and (item is None or (for_new_entry and not item.is_active)):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Variant does not belong to product."
        )
    if item is None or (for_new_entry and not item.is_active):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "This product has variants. Choose a variant.",
        )
    return item.product_name, item.variant_sku or item.sku


def _supplier_product_out(
    entry: SupplierProduct, items: dict[tuple[int, int | None], ProductStockItem]
) -> SupplierProductOut:
    item = items[(entry.product_id, entry.variant_id)]
    return SupplierProductOut(
        id=entry.id,
        supplier_id=entry.supplier_id,
        product_id=entry.product_id,
        variant_id=entry.variant_id,
        supplier_sku=entry.supplier_sku,
        supplier_price=entry.supplier_price,
        product_name=item.product_name,
        product_sku=item.variant_sku or item.sku,
    )


def _catalog_items(
    db: Session, entries: list[SupplierProduct]
) -> dict[tuple[int, int | None], ProductStockItem]:
    return {
        (item.product_id, item.variant_id): item
        for item in product_stock_items(db, {entry.product_id for entry in entries})
    }


@router.get(
    "/suppliers",
    response_model=list[SupplierOut],
    dependencies=[Depends(require(Permission.SUPPLIERS_MANAGE))],
)
def list_suppliers(
    db: DbSession,
    active_only: Annotated[bool, Query()] = False,
) -> list[SupplierOut]:
    query = select(Supplier).order_by(Supplier.name, Supplier.id)
    if active_only:
        query = query.where(Supplier.is_active.is_(True))
    return [SupplierOut.model_validate(row, from_attributes=True) for row in db.scalars(query)]


@router.get(
    "/suppliers/price-history",
    response_model=list[SupplierPriceHistoryOut],
    dependencies=[Depends(require(Permission.SUPPLIERS_MANAGE))],
)
def list_supplier_price_history(
    db: DbSession,
    supplier_id: Annotated[int | None, Query(ge=1)] = None,
    product_id: Annotated[int | None, Query(ge=1)] = None,
) -> list[SupplierPriceHistoryOut]:
    query = (
        select(SupplierPriceHistory, Supplier.name)
        .join(Supplier, Supplier.id == SupplierPriceHistory.supplier_id)
        .order_by(SupplierPriceHistory.recorded_at, SupplierPriceHistory.id)
    )
    if supplier_id is not None:
        query = query.where(SupplierPriceHistory.supplier_id == supplier_id)
    if product_id is not None:
        query = query.where(SupplierPriceHistory.product_id == product_id)
    rows = db.execute(query).all()
    items = {
        (item.product_id, item.variant_id): item
        for item in product_stock_items(
            db, {history.product_id for history, _supplier_name in rows}
        )
    }
    results = []
    for history, supplier_name in rows:
        item = items.get((history.product_id, history.variant_id))
        if item is None:
            raise RuntimeError(f"Missing product metadata for supplier price history {history.id}.")
        results.append(
            SupplierPriceHistoryOut(
                id=history.id,
                supplier_id=history.supplier_id,
                supplier_name=supplier_name,
                product_id=history.product_id,
                product_name=item.product_name,
                variant_id=history.variant_id,
                sku=item.variant_sku or item.sku,
                unit_price=history.unit_price,
                recorded_at=history.recorded_at,
                receipt_line_id=history.receipt_line_id,
            )
        )
    return results


@router.post(
    "/suppliers",
    response_model=SupplierOut,
    status_code=status.HTTP_201_CREATED,
)
def create_supplier(
    body: SupplierInput,
    db: DbSession,
    user: Annotated[CurrentUser, Depends(require(Permission.SUPPLIERS_MANAGE))],
) -> SupplierOut:
    _validate_email(body.email)
    supplier = Supplier(**body.model_dump())
    db.add(supplier)
    try:
        db.flush()
    except IntegrityError as error:
        constraint = _constraint_name(error)
        db.rollback()
        if constraint == "uq_suppliers_name":
            raise HTTPException(status.HTTP_409_CONFLICT, "Supplier name already exists.") from None
        raise
    _audit(
        db,
        user,
        action="supplier_created",
        entity_type="supplier",
        entity_id=supplier.id,
        after={"name": supplier.name, "email": supplier.email, "is_active": True},
    )
    _commit(db, duplicate_message="Supplier name already exists.")
    db.refresh(supplier)
    return SupplierOut.model_validate(supplier, from_attributes=True)


@router.patch(
    "/suppliers/{supplier_id}",
    response_model=SupplierOut,
)
def update_supplier(
    supplier_id: int,
    body: SupplierUpdate,
    db: DbSession,
    user: Annotated[CurrentUser, Depends(require(Permission.SUPPLIERS_MANAGE))],
) -> SupplierOut:
    supplier = _supplier_or_404(db, supplier_id)
    values = body.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Provide at least one field.")
    if "name" in values and values["name"] is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Supplier name cannot be null.")
    if "email" in values:
        _validate_email(values["email"])

    before = {field: getattr(supplier, field) for field in values}
    for field, value in values.items():
        setattr(supplier, field, value)
    try:
        db.flush()
    except IntegrityError as error:
        constraint = _constraint_name(error)
        db.rollback()
        if constraint == "uq_suppliers_name":
            raise HTTPException(status.HTTP_409_CONFLICT, "Supplier name already exists.") from None
        raise
    after = {field: getattr(supplier, field) for field in values}
    _audit(
        db,
        user,
        action="supplier_updated",
        entity_type="supplier",
        entity_id=supplier.id,
        before=before,
        after=after,
    )
    _commit(db, duplicate_message="Supplier name already exists.")
    db.refresh(supplier)
    return SupplierOut.model_validate(supplier, from_attributes=True)


@router.delete(
    "/suppliers/{supplier_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def deactivate_supplier(
    supplier_id: int,
    db: DbSession,
    user: Annotated[CurrentUser, Depends(require(Permission.SUPPLIERS_MANAGE))],
) -> None:
    supplier = _supplier_or_404(db, supplier_id)
    if not supplier.is_active:
        return
    has_open_orders = db.scalar(
        select(PurchaseOrder.id)
        .where(
            PurchaseOrder.supplier_id == supplier_id,
            PurchaseOrder.status.in_(OPEN_ORDER_STATUSES),
        )
        .limit(1)
    )
    if has_open_orders is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Cannot delete supplier with open purchase orders"
        )
    supplier.is_active = False
    _audit(
        db,
        user,
        action="supplier_deactivated",
        entity_type="supplier",
        entity_id=supplier.id,
        before={"is_active": True},
        after={"is_active": False},
    )
    _commit(db)


@router.get(
    "/suppliers/{supplier_id}/products",
    response_model=list[SupplierProductOut],
    dependencies=[Depends(require(Permission.SUPPLIERS_MANAGE))],
)
def list_supplier_products(supplier_id: int, db: DbSession) -> list[SupplierProductOut]:
    _supplier_or_404(db, supplier_id)
    rows = db.scalars(
        select(SupplierProduct)
        .where(SupplierProduct.supplier_id == supplier_id)
        .order_by(SupplierProduct.product_id, SupplierProduct.variant_id, SupplierProduct.id)
    ).all()
    items = _catalog_items(db, list(rows))
    return [_supplier_product_out(row, items) for row in rows]


@router.post(
    "/suppliers/{supplier_id}/products",
    response_model=SupplierProductOut,
    status_code=status.HTTP_201_CREATED,
)
def add_supplier_product(
    supplier_id: int,
    body: SupplierProductCreate,
    db: DbSession,
    user: Annotated[CurrentUser, Depends(require(Permission.SUPPLIERS_MANAGE))],
) -> SupplierProductOut:
    _active_supplier(db, supplier_id)
    product_name, product_sku = _product_item(
        db, body.product_id, body.variant_id, for_new_entry=True
    )
    existing = db.scalar(
        select(SupplierProduct.id).where(
            SupplierProduct.supplier_id == supplier_id,
            SupplierProduct.product_id == body.product_id,
            SupplierProduct.variant_id.is_(None)
            if body.variant_id is None
            else SupplierProduct.variant_id == body.variant_id,
        )
    )
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Product is already in supplier catalog.")
    entry = SupplierProduct(supplier_id=supplier_id, **body.model_dump())
    db.add(entry)
    try:
        db.flush()
    except IntegrityError as error:
        constraint = _constraint_name(error)
        db.rollback()
        if constraint == "uq_supplier_products_supplier_id_product_id_variant_id":
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Product is already in supplier catalog."
            ) from None
        raise
    _audit(
        db,
        user,
        action="supplier_product_added",
        entity_type="supplier_product",
        entity_id=entry.id,
        after={
            "supplier_id": supplier_id,
            "product_id": entry.product_id,
            "variant_id": entry.variant_id,
            "supplier_sku": entry.supplier_sku,
            "supplier_price": str(entry.supplier_price),
        },
    )
    _commit(db)
    db.refresh(entry)
    return SupplierProductOut(
        id=entry.id,
        supplier_id=entry.supplier_id,
        product_id=entry.product_id,
        variant_id=entry.variant_id,
        supplier_sku=entry.supplier_sku,
        supplier_price=entry.supplier_price,
        product_name=product_name,
        product_sku=product_sku,
    )


@router.patch(
    "/suppliers/{supplier_id}/products/{entry_id}",
    response_model=SupplierProductOut,
)
def update_supplier_product(
    supplier_id: int,
    entry_id: int,
    body: SupplierProductUpdate,
    db: DbSession,
    user: Annotated[CurrentUser, Depends(require(Permission.SUPPLIERS_MANAGE))],
) -> SupplierProductOut:
    _active_supplier(db, supplier_id)
    entry = db.scalar(
        select(SupplierProduct).where(
            SupplierProduct.id == entry_id, SupplierProduct.supplier_id == supplier_id
        )
    )
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Supplier product not found.")
    values = body.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Provide at least one field.")
    if "supplier_price" in values and values["supplier_price"] is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Supplier price cannot be null.")
    before = {
        field: str(getattr(entry, field)) if field == "supplier_price" else getattr(entry, field)
        for field in values
    }
    for field, value in values.items():
        setattr(entry, field, value)
    after = {
        field: str(getattr(entry, field)) if field == "supplier_price" else getattr(entry, field)
        for field in values
    }
    _audit(
        db,
        user,
        action="supplier_product_updated",
        entity_type="supplier_product",
        entity_id=entry.id,
        before=before,
        after=after,
    )
    _commit(db)
    db.refresh(entry)
    return _supplier_product_out(entry, _catalog_items(db, [entry]))


@router.delete(
    "/suppliers/{supplier_id}/products/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_supplier_product(
    supplier_id: int,
    entry_id: int,
    db: DbSession,
    user: Annotated[CurrentUser, Depends(require(Permission.SUPPLIERS_MANAGE))],
) -> None:
    _active_supplier(db, supplier_id)
    entry = db.scalar(
        select(SupplierProduct).where(
            SupplierProduct.id == entry_id, SupplierProduct.supplier_id == supplier_id
        )
    )
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Supplier product not found.")
    before = {
        "product_id": entry.product_id,
        "variant_id": entry.variant_id,
        "supplier_sku": entry.supplier_sku,
        "supplier_price": str(entry.supplier_price),
    }
    _audit(
        db,
        user,
        action="supplier_product_removed",
        entity_type="supplier_product",
        entity_id=entry.id,
        before=before,
    )
    db.delete(entry)
    _commit(db)


router.include_router(purchase_orders_router)
