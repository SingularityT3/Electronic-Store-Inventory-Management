"""Sales transactions, returns, invoices.

Public surface of the `sales` module. Other modules may import from here only;
`_internal` is private to this module.
"""

from app.modules.sales.service import SalesService

__all__ = ["SalesService"]
