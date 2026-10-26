"""Public service interface of the `product` module."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.product._internal.models import Category, Product, ProductVariant


@dataclass(frozen=True)
class ProductStockItem:
    """A stockable item: a product's base item (`variant_id` None) or one of its variants.

    Every product and variant is listed, so stock rows, PO lines and catalog entries made
    earlier always resolve to a label. `is_active` says whether the item may take new stock,
    purchase orders or supplier catalog entries: an active variant of an active product, or
    the base item of an active product that has no active variants (stock is held per
    variant once a product has them).
    """

    product_id: int
    product_name: str
    sku: str
    category_id: int
    category_name: str
    variant_id: int | None
    variant_sku: str | None
    variant_attributes: dict[str, Any] | None
    is_active: bool = True
    tracking_mode: str = "untracked"


@dataclass(frozen=True)
class SaleProduct:
    product_id: int
    product_name: str
    product_active: bool
    has_active_variants: bool
    variant_id: int | None
    variant_sku: str | None
    variant_attributes: dict[str, Any] | None
    variant_active: bool
    unit_price: Decimal
    tracking_mode: str = "untracked"


def product_stock_items(
    db: Session, product_ids: Iterable[int] | None = None
) -> list[ProductStockItem]:
    """Return product and variant labels needed to display stock without exposing models.

    Pass `product_ids` to read only those products' items.
    """
    product_query = (
        select(
            Product.id,
            Product.name,
            Product.sku,
            Product.category_id,
            Category.name,
            Product.is_active,
            Product.tracking_mode,
        )
        .join(Category, Category.id == Product.category_id)
        .order_by(Product.name, Product.sku)
    )
    variant_query = select(
        ProductVariant.product_id,
        ProductVariant.id,
        ProductVariant.sku,
        ProductVariant.attributes,
        ProductVariant.is_active,
    ).order_by(ProductVariant.product_id, ProductVariant.sku)
    if product_ids is not None:
        ids = list(product_ids)
        product_query = product_query.where(Product.id.in_(ids))
        variant_query = variant_query.where(ProductVariant.product_id.in_(ids))

    variants_by_product: dict[int, list[tuple[int, str, dict[str, Any], bool]]] = {}
    for product_id, variant_id, variant_sku, attributes, active in db.execute(variant_query):
        variants_by_product.setdefault(product_id, []).append(
            (variant_id, variant_sku, attributes, active)
        )

    items = []
    for (
        product_id,
        name,
        sku,
        category_id,
        category_name,
        product_active,
        tracking_mode,
    ) in db.execute(product_query):
        product_variants = variants_by_product.get(product_id, [])
        has_active_variants = any(active for *_, active in product_variants)
        items.append(
            ProductStockItem(
                product_id,
                name,
                sku,
                category_id,
                category_name,
                None,
                None,
                None,
                product_active and not has_active_variants,
                tracking_mode,
            )
        )
        items.extend(
            ProductStockItem(
                product_id,
                name,
                sku,
                category_id,
                category_name,
                variant_id,
                variant_sku,
                attributes,
                product_active and variant_active,
                tracking_mode,
            )
            for variant_id, variant_sku, attributes, variant_active in product_variants
        )
    return items


def product_stock_item(
    db: Session, product_id: int, variant_id: int | None
) -> ProductStockItem | None:
    """One product or variant item, or None if it does not exist (active or not)."""
    return next(
        (item for item in product_stock_items(db, [product_id]) if item.variant_id == variant_id),
        None,
    )


def lock_product_for_stock(db: Session, product_id: int) -> None:
    """Share-lock tracking configuration until the stock transaction completes."""
    db.scalar(select(Product.id).where(Product.id == product_id).with_for_update(read=True))


def sale_product(db: Session, product_id: int, variant_id: int | None) -> SaleProduct | None:
    """Return the active-sale snapshot and live effective price for one catalog item."""
    product = db.scalar(select(Product).where(Product.id == product_id))
    if product is None:
        return None
    variants = list(
        db.scalars(
            select(ProductVariant).where(
                ProductVariant.product_id == product_id,
                ProductVariant.is_active,
            )
        )
    )
    has_active_variants = bool(variants)
    if variant_id is None:
        if has_active_variants:
            return SaleProduct(
                product_id,
                product.name,
                product.is_active,
                True,
                None,
                None,
                None,
                False,
                product.price,
                product.tracking_mode,
            )
        return SaleProduct(
            product_id,
            product.name,
            product.is_active,
            False,
            None,
            None,
            None,
            False,
            product.price,
            product.tracking_mode,
        )
    variant = db.scalar(
        select(ProductVariant).where(
            ProductVariant.id == variant_id,
            ProductVariant.product_id == product_id,
        )
    )
    if variant is None:
        return None
    return SaleProduct(
        product_id,
        product.name,
        product.is_active,
        has_active_variants,
        variant.id,
        variant.sku,
        variant.attributes,
        variant.is_active,
        variant.price if variant.price is not None else product.price,
        product.tracking_mode,
    )


class ProductService(Protocol):
    """Operations the `product` module offers to other modules.

    Methods are added as features land; callers depend on this interface,
    never on `_internal`.
    """

    # Keep catalog consumers dependent on this public contract rather than private models.


class StockCheck(Protocol):
    def __call__(
        self,
        db: Session,
        product_ids: int | Sequence[int],
        location_id: int | None = None,
        all_locations: bool = True,
    ) -> dict[int, dict[int | None, int]]: ...
