"""Product catalog, categories, variants, search.

Public surface of the `product` module. Other modules may import from here only;
`_internal` is private to this module.
"""

from app.modules.product.service import (
    ProductService,
    ProductStockItem,
    SaleProduct,
    StockCheck,
    product_stock_item,
    product_stock_items,
    sale_product,
)

__all__ = [
    "ProductService",
    "ProductStockItem",
    "SaleProduct",
    "StockCheck",
    "product_stock_item",
    "product_stock_items",
    "sale_product",
]
