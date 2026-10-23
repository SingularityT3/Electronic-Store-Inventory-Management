"""Per-location stock levels, movements, adjustments, transfers, batches/serials.

Public surface of the `stock` module. Other modules may import from here only;
`_internal` is private to this module.
"""

from app.modules.stock.service import (
    InsufficientStockError,
    StockPosition,
    StockService,
    StockUpdateResult,
    location_exists,
    stock_positions,
    update_stock,
)

__all__ = [
    "InsufficientStockError",
    "StockPosition",
    "StockService",
    "StockUpdateResult",
    "location_exists",
    "stock_positions",
    "update_stock",
]
