"""Product catalog, categories, variants, search.

Public surface of the `product` module. Other modules may import from here only;
`_internal` is private to this module.
"""

from app.modules.product.service import ProductService, ProductStockItem, product_stock_items

__all__ = ["ProductService", "ProductStockItem", "product_stock_items"]
