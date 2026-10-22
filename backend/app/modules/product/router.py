"""HTTP routes for the product catalog and its images."""

from decimal import Decimal
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
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
    price: Decimal = Field(ge=0, max_digits=12, decimal_places=2, allow_inf_nan=False)
    description: str | None = None


class ProductOut(ProductInput):
    id: int
    is_active: bool
    category_name: str
    category_path: list[dict[str, int | str]]
    category_path_label: str


class ProductPage(BaseModel):
    items: list[ProductOut]
    total: int
    page: int
    page_size: int


class CategoryOut(BaseModel):
    id: int
    name: str
    parent_id: int | None
    depth: int
    path: list[dict[str, int | str]]
    path_label: str
    product_count: int
    total_product_count: int


class CategoryInput(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    parent_id: int | None = None


class CategoryProductOut(BaseModel):
    id: int
    name: str
    sku: str
    brand: str
    price: Decimal
    category_path: list[dict[str, int | str]]
    category_path_label: str


class CategoryProductPage(BaseModel):
    items: list[CategoryProductOut]
    total: int
    page: int
    page_size: int


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
    if db.scalar(select(Category.id).where(Category.id == body.category_id)) is None:
        _error("category_id", "Unknown category")
    product_sku = select(Product.id).where(func.lower(Product.sku) == sku.lower())
    variant_sku = select(ProductVariant.id).where(func.lower(ProductVariant.sku) == sku.lower())
    if product_id is not None:
        product_sku = product_sku.where(Product.id != product_id)
    if db.scalar(product_sku) is not None or db.scalar(variant_sku) is not None:
        _error("sku", "SKU already exists")
    return name, sku


def _product_out(
    product: Product, category_name: str, category_path: list[dict[str, int | str]]
) -> ProductOut:
    return ProductOut(
        id=product.id,
        name=product.name,
        sku=product.sku,
        category_id=product.category_id,
        category_name=category_name,
        category_path=category_path,
        category_path_label=" > ".join(str(item["name"]) for item in category_path),
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


CATEGORY_TREE_LOCK = 4815162342


def _lock_category_tree(db: Session) -> None:
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": CATEGORY_TREE_LOCK})


def _category_rows(db: Session) -> list[CategoryOut]:
    rows = db.execute(
        text(
            """
            WITH RECURSIVE tree AS (
                SELECT c.id, c.name, c.parent_id, 0 AS depth,
                       ARRAY[c.id] AS id_path, ARRAY[c.name::text] AS name_path
                FROM categories c
                WHERE c.parent_id IS NULL
                UNION ALL
                SELECT c.id, c.name, c.parent_id, tree.depth + 1,
                       tree.id_path || c.id, tree.name_path || c.name
                FROM categories c
                JOIN tree ON tree.id = c.parent_id
            )
            SELECT tree.id, tree.name, tree.parent_id, tree.depth,
                   tree.id_path, tree.name_path,
                   count(p.id) FILTER (WHERE p.is_active)::int AS product_count,
                   (
                       SELECT count(p2.id)::int
                       FROM tree descendant
                       JOIN products p2 ON p2.category_id = descendant.id AND p2.is_active
                       WHERE tree.id = ANY(descendant.id_path)
                   ) AS total_product_count
            FROM tree
            LEFT JOIN products p ON p.category_id = tree.id
            GROUP BY tree.id, tree.name, tree.parent_id, tree.depth, tree.id_path, tree.name_path
            ORDER BY tree.name_path, tree.id
            """
        )
    ).mappings()
    return [
        CategoryOut(
            id=row["id"],
            name=row["name"],
            parent_id=row["parent_id"],
            depth=row["depth"],
            path=[
                {"id": item_id, "name": item_name}
                for item_id, item_name in zip(row["id_path"], row["name_path"], strict=True)
            ],
            path_label=" > ".join(row["name_path"]),
            product_count=row["product_count"] or 0,
            total_product_count=row["total_product_count"] or 0,
        )
        for row in rows
    ]


def _category_or_404(category_id: int, db: Session) -> CategoryOut:
    category = next((item for item in _category_rows(db) if item.id == category_id), None)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    return category


def _category_path_map(db: Session) -> dict[int, list[dict[str, int | str]]]:
    return {item.id: item.path for item in _category_rows(db)}


@router.get("/categories", response_model=list[CategoryOut])
def categories(
    db: DbSession, _user: Annotated[CurrentUser, Depends(require(Permission.PRODUCTS_VIEW))]
) -> list[CategoryOut]:
    return _category_rows(db)


@router.get("/categories/{category_id}", response_model=CategoryOut)
def get_category(
    category_id: int,
    db: DbSession,
    _user: Annotated[CurrentUser, Depends(require(Permission.PRODUCTS_VIEW))],
) -> CategoryOut:
    return _category_or_404(category_id, db)


@router.get("/categories/{category_id}/products", response_model=CategoryProductPage)
def category_products(
    category_id: int,
    db: DbSession,
    _user: Annotated[CurrentUser, Depends(require(Permission.PRODUCTS_VIEW))],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
) -> CategoryProductPage:
    _category_or_404(category_id, db)
    rows = list(
        db.execute(
            text(
                """
            WITH RECURSIVE descendants AS (
                SELECT id FROM categories WHERE id = :category_id
                UNION ALL
                SELECT c.id FROM categories c JOIN descendants d ON c.parent_id = d.id
            ),
            tree AS (
                SELECT c.id, c.name, c.parent_id, ARRAY[c.id] AS id_path,
                       ARRAY[c.name::text] AS name_path
                FROM categories c WHERE c.parent_id IS NULL
                UNION ALL
                SELECT c.id, c.name, c.parent_id, tree.id_path || c.id,
                       tree.name_path || c.name
                FROM categories c JOIN tree ON tree.id = c.parent_id
            )
            SELECT p.id, p.name, p.sku, p.brand, p.price,
                   tree.id_path, tree.name_path, count(*) OVER() AS total
            FROM products p
            JOIN descendants d ON d.id = p.category_id
            JOIN tree ON tree.id = p.category_id
            WHERE p.is_active
            ORDER BY p.name, p.id
            OFFSET :offset LIMIT :limit
            """
            ),
            {"category_id": category_id, "offset": (page - 1) * page_size, "limit": page_size},
        ).mappings()
    )
    items = [
        CategoryProductOut(
            id=row["id"],
            name=row["name"],
            sku=row["sku"],
            brand=row["brand"],
            price=row["price"],
            category_path=[
                {"id": item_id, "name": item_name}
                for item_id, item_name in zip(row["id_path"], row["name_path"], strict=True)
            ],
            category_path_label=" > ".join(row["name_path"]),
        )
        for row in rows
    ]
    total = rows[0]["total"] if rows else 0
    return CategoryProductPage(items=items, total=total, page=page, page_size=page_size)


def _validate_category_name(name: str | None) -> str:
    if name is None:
        _error("name", "Category name is required")
    name = name.strip()
    if not name:
        _error("name", "Category name is required")
    return name


def _validate_parent(db: Session, parent_id: int | None) -> None:
    if (
        parent_id is not None
        and db.scalar(select(Category.id).where(Category.id == parent_id)) is None
    ):
        _error("parent_id", "Invalid parent category")


def _category_integrity(error: IntegrityError) -> None:
    message = str(error.orig).lower()
    if "categories" in message and "name" in message and "parent_id" in message:
        _error("name", "A category with this name already exists under the selected parent")
    raise error


@router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(
    body: CategoryInput,
    db: DbSession,
    user: Annotated[CurrentUser, Depends(require(Permission.PRODUCTS_MANAGE))],
) -> CategoryOut:
    _lock_category_tree(db)
    name = _validate_category_name(body.name)
    _validate_parent(db, body.parent_id)
    category = Category(name=name, parent_id=body.parent_id)
    db.add(category)
    try:
        db.flush()
    except IntegrityError as error:
        db.rollback()
        _category_integrity(error)
    audit_service.record(
        db,
        module="product",
        action="category_created",
        user_id=user.id,
        username=user.username,
        entity_type="category",
        entity_id=str(category.id),
        after={"name": name, "parent_id": body.parent_id},
    )
    db.commit()
    return _category_or_404(category.id, db)


@router.patch("/categories/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: int,
    body: CategoryInput,
    db: DbSession,
    user: Annotated[CurrentUser, Depends(require(Permission.PRODUCTS_MANAGE))],
) -> CategoryOut:
    _lock_category_tree(db)
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    name = (
        category.name if "name" not in body.model_fields_set else _validate_category_name(body.name)
    )
    parent_id = category.parent_id if "parent_id" not in body.model_fields_set else body.parent_id
    _validate_parent(db, parent_id)
    if parent_id is not None:
        is_descendant = db.scalar(
            text(
                """
                WITH RECURSIVE descendants AS (
                    SELECT id FROM categories WHERE id = :category_id
                    UNION ALL
                    SELECT c.id FROM categories c JOIN descendants d ON c.parent_id = d.id
                )
                SELECT 1 FROM descendants WHERE id = :parent_id
                """
            ),
            {"category_id": category_id, "parent_id": parent_id},
        )
        if is_descendant is not None:
            _error("parent_id", "A category cannot be moved under itself or its own subcategories")
    before = {"name": category.name, "parent_id": category.parent_id}
    category.name, category.parent_id = name, parent_id
    try:
        db.flush()
    except IntegrityError as error:
        db.rollback()
        _category_integrity(error)
    after = {"name": category.name, "parent_id": category.parent_id}
    old, new = changes(before, after)
    if "name" in old:
        audit_service.record(
            db,
            module="product",
            action="category_updated",
            user_id=user.id,
            username=user.username,
            entity_type="category",
            entity_id=str(category.id),
            before={"name": old["name"]},
            after={"name": new["name"]},
        )
    if "parent_id" in old:
        audit_service.record(
            db,
            module="product",
            action="category_moved",
            user_id=user.id,
            username=user.username,
            entity_type="category",
            entity_id=str(category.id),
            before={"parent_id": old["parent_id"]},
            after={"parent_id": new["parent_id"]},
        )
    db.commit()
    return _category_or_404(category.id, db)


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: int,
    db: DbSession,
    user: Annotated[CurrentUser, Depends(require(Permission.PRODUCTS_MANAGE))],
) -> None:
    _lock_category_tree(db)
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    has_child = db.scalar(select(Category.id).where(Category.parent_id == category_id).limit(1))
    has_product = db.scalar(select(Product.id).where(Product.category_id == category_id).limit(1))
    if has_child is not None or has_product is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Cannot delete category with existing subcategories/products",
        )
    before = {"name": category.name, "parent_id": category.parent_id}
    db.delete(category)
    audit_service.record(
        db,
        module="product",
        action="category_deleted",
        user_id=user.id,
        username=user.username,
        entity_type="category",
        entity_id=str(category.id),
        before=before,
    )
    db.commit()


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
    paths = _category_path_map(db)
    return ProductPage(
        items=[
            _product_out(product, category_name, paths.get(product.category_id, []))
            for product, category_name in rows
        ],
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
        description=body.description.strip() if body.description else None,
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
        after={"name": name, "sku": sku, "price": str(body.price)},
    )
    db.commit()
    path = _category_path_map(db).get(product.category_id, [])
    return _product_out(product, path[-1]["name"] if path else "", path)


@router.get("/{product_id}", response_model=ProductOut)
def get_product(
    product_id: int,
    db: DbSession,
    _user: Annotated[CurrentUser, Depends(require(Permission.PRODUCTS_VIEW))],
) -> ProductOut:
    product = _active_product(product_id, db)
    path = _category_path_map(db).get(product.category_id, [])
    return _product_out(product, path[-1]["name"] if path else "", path)


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
        body.description.strip() if body.description else None,
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
    path = _category_path_map(db).get(product.category_id, [])
    return _product_out(product, path[-1]["name"] if path else "", path)


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
def upload_image(
    product_id: int,
    file: Annotated[UploadFile, File()],
    db: DbSession,
    settings: AppSettings,
    user: Annotated[CurrentUser, Depends(require(Permission.PRODUCTS_MANAGE))],
) -> ImageOut:
    _active_product(product_id, db)
    content = file.file.read(settings.product_image_max_bytes + 1)
    if len(content) > settings.product_image_max_bytes:
        _error("file", "Image is too large")
    detected = _image_type(content)
    if detected is None:
        _error("file", "Only JPEG, PNG and WebP images are allowed")
    _media_type, extension = detected
    image_dir = Path(settings.product_image_dir)
    image_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4().hex}{extension}"
    path = image_dir / stored_name
    path.write_bytes(content)
    image = ProductImage(product_id=product_id, file_path=stored_name)
    db.add(image)
    audit_service.record(
        db,
        module="product",
        action="product_image_uploaded",
        user_id=user.id,
        username=user.username,
        entity_type="product_image",
        entity_id=stored_name,
        after={"product_id": product_id, "file_type": detected[0]},
    )
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
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
    image = db.scalar(
        select(ProductImage)
        .join(Product, Product.id == ProductImage.product_id)
        .where(ProductImage.id == image_id, Product.is_active)
    )
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
    user: Annotated[CurrentUser, Depends(require(Permission.PRODUCTS_MANAGE))],
) -> None:
    image = db.scalar(
        select(ProductImage)
        .join(Product, Product.id == ProductImage.product_id)
        .where(ProductImage.id == image_id, Product.is_active)
    )
    if image is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found")
    path = Path(settings.product_image_dir) / image.file_path
    if path.is_file():
        path.unlink()
    db.delete(image)
    audit_service.record(
        db,
        module="product",
        action="product_image_deleted",
        user_id=user.id,
        username=user.username,
        entity_type="product_image",
        entity_id=str(image.id),
        before={"product_id": image.product_id, "file_path": image.file_path},
    )
    db.commit()
