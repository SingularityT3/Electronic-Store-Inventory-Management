"""Sales transactions, returns, invoices.

Public surface of the `sales` module. Other modules may import from here only;
`_internal` is private to this module.
"""

from app.modules.sales.service import (
    InvoiceNotFoundError,
    ReturnCreditNote,
    ReturnCreditNoteLine,
    ReturnLateApprovalRequiredError,
    ReturnLineInput,
    SaleInputError,
    SaleLookupData,
    SaleLookupLineData,
    SalesService,
    SaleStockError,
    SalesTotalsByProduct,
    SaleTrackingError,
    compute_line_refund,
    compute_sale_return_status,
    get_credit_note,
    get_sale_return_status,
    invoice_label,
    lookup_sale_by_invoice,
    parse_invoice_number,
    process_return,
    restore_returned_batch_units,
    restore_returned_serials,
    sales_totals_by_product,
)

__all__ = [
    "InvoiceNotFoundError",
    "ReturnCreditNote",
    "ReturnCreditNoteLine",
    "ReturnLateApprovalRequiredError",
    "ReturnLineInput",
    "SaleInputError",
    "SaleLookupData",
    "SaleLookupLineData",
    "SaleStockError",
    "SaleTrackingError",
    "SalesService",
    "SalesTotalsByProduct",
    "sales_totals_by_product",
    "compute_line_refund",
    "compute_sale_return_status",
    "get_credit_note",
    "get_sale_return_status",
    "lookup_sale_by_invoice",
    "parse_invoice_number",
    "invoice_label",
    "process_return",
    "restore_returned_batch_units",
    "restore_returned_serials",
]
