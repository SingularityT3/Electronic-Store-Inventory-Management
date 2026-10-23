"""Per-location stock levels, movements, adjustments, transfers, batches/serials.

Public surface of the `stock` module. Other modules may import from here only;
`_internal` is private to this module.
"""

from app.modules.stock.service import (
    StockPosition,
    StockService,
    StockTransferError,
    StockTransferResult,
    location_exists,
    stock_positions,
    transfer_stock,
)

__all__ = [
    "StockPosition",
    "StockService",
    "StockTransferError",
    "StockTransferResult",
    "location_exists",
    "stock_positions",
    "transfer_stock",
]
