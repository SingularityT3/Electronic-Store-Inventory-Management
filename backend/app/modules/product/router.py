"""HTTP routes for the product catalog and its images."""

from decimal import Decimal
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_session
from app.modules.audit import audit_service, changes
from app.modules.auth import CurrentUser, Permission, require
from app.modules.product._internal.models import Category, Product, ProductImage, ProductVariant
from app.modules.product.service import StockCheck

router = APIRouter(prefix="/product", tags=["product"])
DbSession = Annotated[Session, Depends(get_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]
_stock_checker: StockCheck | None = None


def set_stock_checker(checker: StockCheck) -> None:
    global _stock_checker
    _stock_checker = checker


class ProductInput(BaseModel):
    name: str = Field(max_length=200)
    sku: str = Field(max_length=64)
    category_id: int
    brand: str = Field(max_length=100)
    price: Decimal
    description: str | None = None


class ProductOut(ProductInput):
    id: int
    is_active: bool
    category_name: str


class ProductPage(BaseModel):
    items: list[ProductOut]
    total: int
    page: int
    page_size: int


class CategoryOut(BaseModel):
    id: int
    name: str
    parent_id: int | None


class ImageOut(BaseModel):
    id: int
    url: str


def _error(field: str, message: str, code: int = status.HTTP_422_UNPROCESSABLE_ENTITY) -> None:
    raise HTTPException(code, {"field": field, "message": message})


def _validate(body: ProductInput, db: Session, product_id: int | None = None) -> tuple[str, str]:
    name, sku = body.name.strip(), body.sku.strip()
    if not name:
        _error("name", "Product Name is required")
    if not sku:
        _error("sku", "SKU is required")
    if body.price < 0:
        _error("price", "Price must be non-negative")
    if db.scalar(select(Category.id).where(Category.id == body.category_id)) is None:
        _error("category_id", "Unknown category")
    product_sku = select(Product.id).where(func.lower(Product.sku) == sku.lower())
    variant_sku = select(ProductVariant.id).where(func.lower(ProductVariant.sku) == sku.lower())
    if product_id is not None:
        product_sku = product_sku.where(Product.id != product_id)
    if db.scalar(product_sku) is not None or db.scalar(variant_sku) is not None:
        _error("sku", "SKU already exists")
    return name, sku


def _product_out(product: Product, category_name: str) -> ProductOut:
    return ProductOut(
        id=product.id,
        name=product.name,
        sku=product.sku,
        category_id=product.category_id,
        category_name=category_name,
        brand=product.brand,
        price=product.price,
        description=product.description,
        is_active=product.is_active,
    )


def _duplicate(error: IntegrityError) -> bool:
    text = str(error.orig).lower()
    return "sku" in text or "enforce_unique_sku" in text


def _active_product(product_id: int, db: Session) -> Product:
    product = db.scalar(select(Product).where(Product.id == product_id, Product.is_active))
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    return product


@router.get("/categories", response_model=list[CategoryOut])
def categories(
    db: DbSession, _user: Annotated[CurrentUser, Depends(require(Permission.PRODUCTS_VIEW))]
) -> list[CategoryOut]:
    return [
        CategoryOut(id=row.id, name=row.name, parent_id=row.parent_id)
        for row in db.scalars(select(Category).order_by(Category.name, Category.id))
    ]


@router.get("", response_model=ProductPage)
def list_products(
    db: DbSession,
    _user: Annotated[CurrentUser, Depends(require(Permission.PRODUCTS_VIEW))],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
) -> ProductPage:
    query = (
        select(Product, Category.name)
        .join(Category, Category.id == Product.category_id)
        .where(Product.is_active)
        .order_by(Product.name, Product.id)
    )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.execute(query.offset((page - 1) * page_size).limit(page_size)).all()
    return ProductPage(
        items=[_product_out(product, category_name) for product, category_name in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(
    body: ProductInput,
    db: DbSession,
    user: Annotated[CurrentUser, Depends(require(Permission.PRODUCTS_MANAGE))],
) -> ProductOut:
    name, sku = _validate(body, db)
    product = Product(
        name=name,
        sku=sku,
        category_id=body.category_id,
        brand=body.brand.strip(),
        price=body.price,
        description=body.description,
    )
    db.add(product)
    try:
        db.flush()
    except IntegrityError as error:
        db.rollback()
        if _duplicate(error):
            _error("sku", "SKU already exists")
        raise
    audit_service.record(
        db,
        module="product",
        action="product_created",
        user_id=user.id,
        username=user.username,
        entity_type="product",
        entity_id=str(product.id),
        after={"name": name, "sku": sku, "price": body.price},
    )
    db.commit()
    category_name = db.scalar(select(Category.name).where(Category.id == product.category_id)) or ""
    return _product_out(product, category_name)


@router.get("/{product_id}", response_model=ProductOut)
def get_product(
    product_id: int,
    db: DbSession,
    _user: Annotated[CurrentUser, Depends(require(Permission.PRODUCTS_VIEW))],
) -> ProductOut:
    product = _active_product(product_id, db)
    category_name = db.scalar(select(Category.name).where(Category.id == product.category_id)) or ""
    return _product_out(product, category_name)


@router.put("/{product_id}", response_model=ProductOut)
def update_product(
    product_id: int,
    body: ProductInput,
    db: DbSession,
    user: Annotated[CurrentUser, Depends(require(Permission.PRODUCTS_MANAGE))],
) -> ProductOut:
    product = _active_product(product_id, db)
    name, sku = _validate(body, db, product.id)
    before = {
        "name": product.name,
        "sku": product.sku,
        "category_id": product.category_id,
        "brand": product.brand,
        "price": product.price,
        "description": product.description,
    }
    product.name, product.sku, product.category_id = name, sku, body.category_id
    product.brand, product.price, product.description = (
        body.brand.strip(),
        body.price,
        body.description,
    )
    try:
        db.flush()
    except IntegrityError as error:
        db.rollback()
        if _duplicate(error):
            _error("sku", "SKU already exists")
        raise
    after = {
        "name": product.name,
        "sku": product.sku,
        "category_id": product.category_id,
        "brand": product.brand,
        "price": product.price,
        "description": product.description,
    }
    old, new = changes(before, after)
    if old:
        action = "product_price_updated" if set(old) == {"price"} else "product_updated"
        audit_service.record(
            db,
            module="product",
            action=action,
            user_id=user.id,
            username=user.username,
            entity_type="product",
            entity_id=str(product.id),
            before=old,
            after=new,
        )
    db.commit()
    category_name = db.scalar(select(Category.name).where(Category.id == product.category_id)) or ""
    return _product_out(product, category_name)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: int,
    db: DbSession,
    user: Annotated[CurrentUser, Depends(require(Permission.PRODUCTS_MANAGE))],
) -> None:
    product = _active_product(product_id, db)
    if _stock_checker is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Stock service unavailable")
    if _stock_checker(db, product_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Cannot delete product with existing stock")
    product.is_active = False
    audit_service.record(
        db,
        module="product",
        action="product_deleted",
        user_id=user.id,
        username=user.username,
        entity_type="product",
        entity_id=str(product.id),
        before={"is_active": True},
        after={"is_active": False},
    )
    db.commit()


def _image_type(content: bytes) -> tuple[str, str] | None:
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp", ".webp"
    return None


@router.post("/{product_id}/images", response_model=ImageOut, status_code=status.HTTP_201_CREATED)
async def upload_image(
    product_id: int,
    file: Annotated[UploadFile, File()],
    db: DbSession,
    settings: AppSettings,
    _user: Annotated[CurrentUser, Depends(require(Permission.PRODUCTS_MANAGE))],
) -> ImageOut:
    _active_product(product_id, db)
    content = await file.read(settings.product_image_max_bytes + 1)
    if len(content) > settings.product_image_max_bytes:
        _error("file", "Image is too large")
    detected = _image_type(content)
    if detected is None:
        _error("file", "Only JPEG, PNG and WebP images are allowed")
    _media_type, extension = detected
    image_dir = Path(settings.product_image_dir)
    image_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4().hex}{extension}"
    (image_dir / stored_name).write_bytes(content)
    image = ProductImage(product_id=product_id, file_path=stored_name)
    db.add(image)
    db.commit()
    return ImageOut(id=image.id, url=f"/product/images/{image.id}")


@router.get("/{product_id}/images", response_model=list[ImageOut])
def list_images(
    product_id: int,
    db: DbSession,
    _user: Annotated[CurrentUser, Depends(require(Permission.PRODUCTS_VIEW))],
) -> list[ImageOut]:
    _active_product(product_id, db)
    return [
        ImageOut(id=image.id, url=f"/product/images/{image.id}")
        for image in db.scalars(
            select(ProductImage)
            .where(ProductImage.product_id == product_id)
            .order_by(ProductImage.sort_order, ProductImage.id)
        )
    ]


@router.get("/images/{image_id}")
def serve_image(
    image_id: int,
    db: DbSession,
    settings: AppSettings,
    _user: Annotated[CurrentUser, Depends(require(Permission.PRODUCTS_VIEW))],
) -> FileResponse:
    image = db.get(ProductImage, image_id)
    if image is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found")
    path = Path(settings.product_image_dir) / image.file_path
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found")
    media_type = {
        ".jpg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(path.suffix)
    response = FileResponse(path, media_type=media_type)
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@router.delete("/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_image(
    image_id: int,
    db: DbSession,
    settings: AppSettings,
    _user: Annotated[CurrentUser, Depends(require(Permission.PRODUCTS_MANAGE))],
) -> None:
    image = db.get(ProductImage, image_id)
    if image is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found")
    path = Path(settings.product_image_dir) / image.file_path
    if path.is_file():
        path.unlink()
    db.delete(image)
    db.commit()
