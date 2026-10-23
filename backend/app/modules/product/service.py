"""Public service interface of the `product` module."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.product._internal.models import Category, Product, ProductVariant


@dataclass(frozen=True)
class ProductStockItem:
    product_id: int
    product_name: str
    sku: str
    category_id: int
    category_name: str
    variant_id: int | None
    variant_sku: str | None
    variant_attributes: dict[str, Any] | None


def product_stock_items(db: Session) -> list[ProductStockItem]:
    """Return product and variant labels needed to display stock without exposing models."""
    products = db.execute(
        select(Product.id, Product.name, Product.sku, Product.category_id, Category.name)
        .join(Category, Category.id == Product.category_id)
        .order_by(Product.name, Product.sku)
    ).all()
    variants = db.execute(
        select(
            ProductVariant.product_id,
            ProductVariant.id,
            ProductVariant.sku,
            ProductVariant.attributes,
        ).order_by(ProductVariant.product_id, ProductVariant.sku)
    ).all()
    variants_by_product: dict[int, list[tuple[int, str, dict[str, Any]]]] = {}
    for product_id, variant_id, variant_sku, attributes in variants:
        variants_by_product.setdefault(product_id, []).append((variant_id, variant_sku, attributes))

    items = []
    for product_id, name, sku, category_id, category_name in products:
        product_variants = variants_by_product.get(product_id, [])
        if product_variants:
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
                )
                for variant_id, variant_sku, attributes in product_variants
            )
        else:
            items.append(
                ProductStockItem(
                    product_id, name, sku, category_id, category_name, None, None, None
                )
            )
    return items


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
