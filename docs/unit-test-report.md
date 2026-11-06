# Unit and integration test report

Final results for the unit (UT) and integration (IT) cases of
[`Documents/Test_Plan_Document.docx`](../Documents/Test_Plan_Document.docx). The filled-in plan holds
the same results per case (Actual Result and Test Result columns). System tests are in
[`system-validation-report.md`](system-validation-report.md); coverage is in
[`code-coverage-report.md`](code-coverage-report.md) and
[`branch-coverage-report.md`](branch-coverage-report.md).

## Result

**All 169 unit and integration cases pass (83 UT, 86 IT), and every automated test in the repository passes.**

| Suite | Tests | Passed | Failed | Skipped |
|---|---:|---:|---:|---:|
| Backend (pytest) | 355 | 355 | 0 | 0 |
| Frontend (Vitest, 25 test files) | 137 | 137 | 0 | 0 |
| **Total** | **492** | **492** | **0** | **0** |

No defects were raised by this run.

Run note: the first full backend run reported one failure,
`tests/test_architecture.py::test_module_boundaries_respected`, with `FileNotFoundError: 'lint-imports'`.
The test shells out to the `lint-imports` command and the virtual environment's `bin` directory was not on
`PATH`. It is an environment problem, not a code defect: with `PATH` corrected the test passes, the
full suite was run again from scratch, and the table above is from that second run.

## Environment

- Run date: 2026-11-06
- Backend: Python 3.13.18, pytest 8.3.4, coverage.py 7.17.2 (via pytest-cov), PostgreSQL 16.15
- Frontend: Node 22.23.4, Vitest 3.2.7 (jsdom), @vitest/coverage-v8 3.2.7
- Code under test: `main` at commit `b769635` (merge of pull request #90), unmodified

Docker was not available in the session that produced these numbers, so the suites ran directly
on the host (a Python virtual environment with `backend/requirements-dev.txt`, a local PostgreSQL 16
server, and `npm ci` for the frontend) instead of in the project's containers. The containers use
Python 3.12 and `postgres:16-alpine`. The tests create their own throwaway databases, so the
method is the same, but the interpreter and database build differ slightly from the CI images.

## How it was run

```bash
# backend (needs the db service; the tests create and drop their own databases)
docker compose run --rm backend sh -c "pip install -q pytest-cov && pytest --cov=app --cov-branch -v"
# frontend
docker compose run --rm --no-deps frontend npm test
```

`pytest-cov` is not in `requirements-dev.txt`, so it is installed on the fly. Case-to-test mapping comes
from [`backend/tests/TRACEABILITY.md`](../backend/tests/TRACEABILITY.md), which
`tests/test_traceability.py` keeps in step with the plan and the test code.

## Static checks

| Check | Command | Result |
|---|---|---|
| Backend lint | `ruff check .` | All checks passed |
| Backend format | `ruff format --check .` | 133 files already formatted |
| Module boundaries | `lint-imports` (also run by `tests/test_architecture.py`) | 9 contracts kept, 0 broken |
| Frontend lint and format | `npm run lint` (ESLint, Prettier) | Clean |
| Frontend type check and build | `npm run build` (`tsc -b`, `vite build`) | Built, no type errors |

## Results by module

Unit cases:

| Module | Cases | Pass | Fail |
|---|---:|---:|---:|
| 3.1 Product Management | 9 | 9 | 0 |
| 3.2 Stock Management | 15 | 15 | 0 |
| 3.3 Purchasing / Supplier Management | 12 | 12 | 0 |
| 3.4 Sales / Orders | 9 | 9 | 0 |
| 3.5 User Management | 9 | 9 | 0 |
| 3.6 Reporting and Analytics | 15 | 15 | 0 |
| 3.7 Search and Filter | 6 | 6 | 0 |
| 3.8 Notifications | 6 | 6 | 0 |
| 3.9 Security | 2 | 2 | 0 |
| **Total** | **83** | **83** | **0** |

Integration cases:

| Module | Cases | Pass | Fail |
|---|---:|---:|---:|
| 3.1 Product Management | 9 | 9 | 0 |
| 3.2 Stock Management | 15 | 15 | 0 |
| 3.3 Purchasing / Supplier Management | 12 | 12 | 0 |
| 3.4 Sales / Orders | 9 | 9 | 0 |
| 3.5 User Management | 9 | 9 | 0 |
| 3.6 Reporting and Analytics | 15 | 15 | 0 |
| 3.7 Search and Filter | 6 | 6 | 0 |
| 3.8 Notifications | 6 | 6 | 0 |
| 3.9 Security | 5 | 5 | 0 |
| **Total** | **86** | **86** | **0** |

## Test inventory

218 of the 355 backend tests and 45 of the 137 frontend tests are named in the
traceability table. The rest are additional regression tests (constraints, migrations, retention, backup,
seed data, architecture, CSRF and similar) that are not tied to one plan case.

| Backend test file | Tests | Time (s) |
|---|---:|---:|
| `test_architecture.py` | 1 | 0.1 |
| `test_audit.py` | 25 | 3.2 |
| `test_auth.py` | 25 | 3.4 |
| `test_backup.py` | 10 | 0.0 |
| `test_batch_serial_tracking.py` | 10 | 2.5 |
| `test_categories.py` | 3 | 1.3 |
| `test_constraints.py` | 20 | 0.1 |
| `test_create_admin.py` | 7 | 2.9 |
| `test_csrf.py` | 4 | 0.6 |
| `test_health.py` | 2 | 0.0 |
| `test_invoices.py` | 16 | 5.4 |
| `test_migrations.py` | 5 | 1.4 |
| `test_notifications.py` | 9 | 4.2 |
| `test_plan_cases.py` | 15 | 3.4 |
| `test_product_filters.py` | 3 | 1.3 |
| `test_product_search.py` | 3 | 2.0 |
| `test_products.py` | 4 | 1.7 |
| `test_purchase_order_lifecycle.py` | 7 | 3.1 |
| `test_purchase_order_receiving.py` | 8 | 1.8 |
| `test_purchase_orders.py` | 10 | 2.3 |
| `test_rbac.py` | 17 | 5.3 |
| `test_reporting_export.py` | 25 | 6.6 |
| `test_reporting_stock.py` | 6 | 0.8 |
| `test_retention.py` | 6 | 0.0 |
| `test_returns.py` | 12 | 4.3 |
| `test_returns_concurrency.py` | 2 | 0.6 |
| `test_sales.py` | 16 | 4.1 |
| `test_sales_availability.py` | 2 | 0.3 |
| `test_sales_trend.py` | 4 | 0.5 |
| `test_seed.py` | 1 | 0.9 |
| `test_stock_adjustments.py` | 6 | 0.8 |
| `test_stock_items.py` | 5 | 0.6 |
| `test_stock_levels.py` | 2 | 0.3 |
| `test_stock_locations.py` | 7 | 1.7 |
| `test_stock_transfers.py` | 12 | 3.0 |
| `test_supplier_performance.py` | 7 | 1.4 |
| `test_supplier_price_history.py` | 2 | 0.8 |
| `test_suppliers.py` | 10 | 2.0 |
| `test_traceability.py` | 4 | 0.0 |
| `test_uptime.py` | 5 | 0.0 |
| `test_usability_summary.py` | 4 | 0.0 |
| `test_users.py` | 10 | 2.8 |
| `test_variants.py` | 3 | 0.9 |

| Frontend test file | Tests | Time (s) |
|---|---:|---:|
| `frontend/src/api.test.ts` | 2 | 0.01 |
| `frontend/src/modules/audit/audit.test.tsx` | 9 | 0.97 |
| `frontend/src/modules/auth/UsersPage.test.tsx` | 3 | 0.74 |
| `frontend/src/modules/auth/auth.test.tsx` | 7 | 0.65 |
| `frontend/src/modules/notifications/notifications.test.tsx` | 6 | 0.79 |
| `frontend/src/modules/product/product.test.tsx` | 5 | 0.39 |
| `frontend/src/modules/purchasing/POReceivingPage.test.tsx` | 2 | 0.46 |
| `frontend/src/modules/purchasing/PurchaseOrdersPage.test.tsx` | 4 | 0.87 |
| `frontend/src/modules/purchasing/SupplierPriceHistoryPage.test.tsx` | 3 | 0.30 |
| `frontend/src/modules/purchasing/SuppliersPage.test.tsx` | 4 | 0.99 |
| `frontend/src/modules/reporting/LowStockReportPage.test.tsx` | 3 | 0.19 |
| `frontend/src/modules/reporting/StockValuationPage.test.tsx` | 4 | 0.33 |
| `frontend/src/modules/reporting/SupplierPerformanceReportPage.test.tsx` | 4 | 0.49 |
| `frontend/src/modules/sales/AvailabilityPage.test.tsx` | 1 | 0.10 |
| `frontend/src/modules/sales/DocumentPages.test.tsx` | 2 | 0.22 |
| `frontend/src/modules/sales/DocumentView.test.tsx` | 3 | 0.24 |
| `frontend/src/modules/sales/PosPage.test.tsx` | 3 | 0.60 |
| `frontend/src/modules/sales/ReturnsPage.test.tsx` | 10 | 1.57 |
| `frontend/src/modules/stock/BatchRecallPage.test.tsx` | 3 | 0.54 |
| `frontend/src/modules/stock/LocationsPage.test.tsx` | 2 | 0.59 |
| `frontend/src/modules/stock/StockLevelsPage.test.tsx` | 7 | 0.98 |
| `frontend/src/modules/stock/StockTransferPage.test.tsx` | 6 | 0.69 |
| `frontend/src/security.test.tsx` | 3 | 0.37 |
| `frontend/src/shell/components/components.test.tsx` | 13 | 0.33 |
| `frontend/src/shell/shell.test.tsx` | 28 | 1.23 |

## Unit test cases (83)

### 3.1 Product Management

| ID | Description | Evidence | Result |
|---|---|---|---|
| FR1.1-UT-1 | Verify that a product can be added with all valid mandatory fields | `backend/tests/test_products.py::test_manager_creates_and_lists_product` | Pass |
| FR1.1-UT-2 | Verify system rejects adding a product with a duplicate SKU | `backend/tests/test_products.py::test_product_validation_rejects_duplicate_blank_and_negative`<br>`backend/tests/test_constraints.py::test_duplicate_product_sku_rejected` | Pass |
| FR1.1-UT-3 | Verify mandatory field validation when Product Name is left blank | `backend/tests/test_products.py::test_product_validation_rejects_duplicate_blank_and_negative` | Pass |
| FR1.2-UT-1 | Verify a new top-level category can be created successfully | `backend/tests/test_categories.py::test_admin_creates_tree_in_tree_order_and_invalid_parent_is_not_saved` | Pass |
| FR1.2-UT-2 | Verify a subcategory can be created under an existing valid parent category | `backend/tests/test_categories.py::test_admin_creates_tree_in_tree_order_and_invalid_parent_is_not_saved` | Pass |
| FR1.2-UT-3 | Verify system prevents creating a subcategory referencing a non-existent/deleted parent category ID | `backend/tests/test_categories.py::test_admin_creates_tree_in_tree_order_and_invalid_parent_is_not_saved` | Pass |
| FR1.3-UT-1 | Verify a product variant can be added with valid attribute values | `backend/tests/test_variants.py::test_variants_normalize_attributes_and_use_effective_price` | Pass |
| FR1.3-UT-2 | Verify system prevents creating a duplicate variant (same combination of attributes) for the same product | `backend/tests/test_variants.py::test_duplicate_variant_combination_and_sku_are_field_errors`<br>`backend/tests/test_constraints.py::test_duplicate_variant_combination_rejected` | Pass |
| FR1.3-UT-3 | Verify a variant can be created with a different attribute combination for the same base product | `backend/tests/test_variants.py::test_variants_normalize_attributes_and_use_effective_price` | Pass |

### 3.2 Stock Management

| ID | Description | Evidence | Result |
|---|---|---|---|
| FR2.1-UT-1 | Verify stock level can be recorded and viewed for a product at a specific store location | `backend/tests/test_stock_levels.py::test_stock_levels_are_per_location_and_expose_combined_totals` | Pass |
| FR2.1-UT-2 | Verify the same product can have different stock levels at two different locations independently | `backend/tests/test_stock_levels.py::test_stock_levels_are_per_location_and_expose_combined_totals` | Pass |
| FR2.1-UT-3 | Verify system rejects setting a negative stock quantity | `backend/tests/test_constraints.py::test_negative_stock_rejected`<br>`backend/tests/test_stock_adjustments.py::test_adjustment_below_zero_is_blocked` | Pass |
| FR2.2-UT-1 | Verify stock automatically decreases when a sales transaction is completed | `backend/tests/test_sales.py::test_fr4_1_ut_2_and_fr2_2_ut_1_stock_drops_by_exactly_the_sold_quantity` | Pass |
| FR2.2-UT-2 | Verify stock automatically increases when a purchase order receipt is recorded | `backend/tests/test_purchase_order_receiving.py::test_full_receipt_updates_stock_cost_history_audit_and_status_notifications` | Pass |
| FR2.2-UT-3 | Verify stock updates correctly on both source and destination when a stock transfer is confirmed | `backend/tests/test_stock_transfers.py::test_transfer_updates_stock_movements_audit_and_valuation` | Pass |
| FR2.3-UT-1 | Verify a low-stock alert is generated when stock falls to or below the configured reorder threshold | `backend/tests/test_notifications.py::test_shared_stock_updates_create_distinct_alerts_and_clear_on_recovery` | Pass |
| FR2.3-UT-2 | Verify an out-of-stock alert is generated distinctly when stock reaches zero | `backend/tests/test_notifications.py::test_shared_stock_updates_create_distinct_alerts_and_clear_on_recovery` | Pass |
| FR2.3-UT-3 | Verify no alert is generated when stock is above the reorder threshold | `backend/tests/test_plan_cases.py::test_fr2_3_ut_3_and_fr8_1_ut_2_alert_only_at_or_below_threshold` | Pass |
| FR2.4-UT-1 | Verify a manual stock adjustment can be recorded with a valid reason | `backend/tests/test_stock_adjustments.py::test_negative_adjustment_reduces_stock_and_logs_reason` | Pass |
| FR2.4-UT-2 | Verify system rejects a stock adjustment submitted without a reason | `backend/tests/test_stock_adjustments.py::test_blank_reason_is_rejected_and_stock_unchanged`<br>`backend/tests/test_constraints.py::test_adjustment_requires_reason` | Pass |
| FR2.4-UT-3 | Verify a positive stock adjustment (correction adding units, e.g. found stock) is processed correctly | `backend/tests/test_stock_adjustments.py::test_positive_adjustment_increases_stock` | Pass |
| FR2.5-UT-1 | Verify a batch number can be assigned when receiving stock for a batch-tracked product | `backend/tests/test_purchase_order_receiving.py::test_receipt_integrates_batch_and_serial_tracking`<br>`backend/tests/test_batch_serial_tracking.py::test_batch_receipt_sale_and_recall_reports_sold_invoice_and_available_units` | Pass |
| FR2.5-UT-2 | Verify a unique serial number can be assigned to an individual unit of a serial-tracked product | `backend/tests/test_purchase_order_receiving.py::test_receipt_integrates_batch_and_serial_tracking`<br>`backend/tests/test_batch_serial_tracking.py::test_serial_receipt_sale_and_return_preserve_invoice_trace` | Pass |
| FR2.5-UT-3 | Verify system rejects entry of a duplicate serial number for the same product | `backend/tests/test_purchase_order_receiving.py::test_duplicate_serial_rolls_back_receipt_and_stock`<br>`backend/tests/test_plan_cases.py::test_fr2_5_ut_3_duplicate_serial_number_is_rejected` | Pass |

### 3.3 Purchasing / Supplier Management

| ID | Description | Evidence | Result |
|---|---|---|---|
| FR3.1-UT-1 | Verify a new supplier record can be created with valid contact details | `backend/tests/test_suppliers.py::test_supplier_crud_validates_email_and_records_audit` | Pass |
| FR3.1-UT-2 | Verify system validates email format when adding a supplier | `backend/tests/test_suppliers.py::test_supplier_crud_validates_email_and_records_audit`<br>`frontend/src/modules/purchasing/SuppliersPage.test.tsx::renders supplier management at the guarded route and handles supplier email errors` | Pass |
| FR3.1-UT-3 | Verify a product can be linked to a supplier's catalog | `backend/tests/test_suppliers.py::test_catalog_crud_validates_prices_references_and_duplicate_associations` | Pass |
| FR3.2-UT-1 | Verify a purchase order can be created with valid supplier and line items | `backend/tests/test_purchase_orders.py::test_create_list_view_edit_and_submit_po_calculates_totals_and_audits` | Pass |
| FR3.2-UT-2 | Verify system prevents creating a PO with zero or negative quantity for a line item | `backend/tests/test_purchase_orders.py::test_purchase_order_rejects_zero_and_negative_quantities` | Pass |
| FR3.2-UT-3 | Verify an existing PO in Draft status can be edited to add/remove line items before submission | `backend/tests/test_purchase_orders.py::test_create_list_view_edit_and_submit_po_calculates_totals_and_audits` | Pass |
| FR3.3-UT-1 | Verify stock can be received in full against an open purchase order | `backend/tests/test_purchase_order_receiving.py::test_full_receipt_updates_stock_cost_history_audit_and_status_notifications` | Pass |
| FR3.3-UT-2 | Verify partial receipt against a PO is recorded correctly and the remaining balance is tracked | `backend/tests/test_purchase_order_receiving.py::test_multiple_receipts_accumulate_and_short_items_remain_outstanding` | Pass |
| FR3.3-UT-3 | Verify system rejects receiving a quantity greater than what remains outstanding on the PO | `backend/tests/test_purchase_order_receiving.py::test_over_receipt_rejects_without_creating_any_receipt_or_stock_changes`<br>`backend/tests/test_purchase_order_receiving.py::test_concurrent_receipts_cannot_exceed_the_outstanding_order_quantity`<br>`backend/tests/test_constraints.py::test_po_line_cannot_receive_more_than_ordered` | Pass |
| FR3.4-UT-1 | Verify a new pricing history entry is automatically created when a purchase order is received at a given unit price | `backend/tests/test_supplier_price_history.py::test_receipts_append_price_history_and_filters_keep_supplier_attribution` | Pass |
| FR3.4-UT-2 | Verify multiple pricing history entries accumulate over time for the same supplier/product without overwriting previous entries | `backend/tests/test_supplier_price_history.py::test_receipts_append_price_history_and_filters_keep_supplier_attribution` | Pass |
| FR3.4-UT-3 | Verify pricing history can be viewed filtered by a specific supplier and product combination | `backend/tests/test_supplier_price_history.py::test_receipts_append_price_history_and_filters_keep_supplier_attribution` | Pass |

### 3.4 Sales / Orders

| ID | Description | Evidence | Result |
|---|---|---|---|
| FR4.1-UT-1 | Verify a sales transaction can be recorded successfully for an in-stock product | `backend/tests/test_sales.py::test_fr4_1_ut_1_cashier_records_a_sale_for_an_in_stock_product` | Pass |
| FR4.1-UT-2 | Verify stock is automatically deducted by the exact sold quantity upon transaction completion | `backend/tests/test_sales.py::test_fr4_1_ut_2_and_fr2_2_ut_1_stock_drops_by_exactly_the_sold_quantity` | Pass |
| FR4.1-UT-3 | Verify system prevents completing a sale for a product with zero available stock | `backend/tests/test_sales.py::test_fr4_1_ut_3_zero_stock_is_out_of_stock_and_nothing_is_recorded` | Pass |
| FR4.2-UT-1 | Verify a return can be processed against a valid original invoice within the return policy window | `backend/tests/test_returns.py::test_fr4_2_ut_1_valid_return_generates_credit_note` | Pass |
| FR4.2-UT-2 | Verify a valid returned item is automatically restocked | `backend/tests/test_returns.py::test_fr4_2_ut_2_resaleable_unit_restocks_inventory` | Pass |
| FR4.2-UT-3 | Verify system rejects a return request referencing an invalid or non-existent invoice number | `backend/tests/test_returns.py::test_fr4_2_ut_3_invoice_lookup_valid_and_invalid` | Pass |
| FR4.3-UT-1 | Verify an invoice is automatically generated upon completion of a sales transaction | `backend/tests/test_invoices.py::test_fr4_3_ut_1_invoice_snapshot_is_available_with_the_sale` | Pass |
| FR4.3-UT-2 | Verify the generated invoice contains all required details: item(s), quantity, unit price, total, tax, date, and cashier ID | `backend/tests/test_invoices.py::test_fr4_3_ut_2_sale_persists_required_invoice_snapshot` | Pass |
| FR4.3-UT-3 | Verify the invoice total correctly matches the sum of line items plus applicable taxes | `backend/tests/test_invoices.py::test_fr4_3_ut_3_two_item_invoice_total_is_lines_plus_gst`<br>`backend/tests/test_invoices.py::test_fr4_3_ut_3_paise_are_rounded_per_line_and_still_add_up` | Pass |

### 3.5 User Management

| ID | Description | Evidence | Result |
|---|---|---|---|
| FR5.1-UT-1 | Verify an Admin can assign a specific role to a newly created user account | `backend/tests/test_users.py::test_admin_creates_manager_and_invite_is_not_exposed` | Pass |
| FR5.1-UT-2 | Verify a Manager-role user can access Product, Stock, Supplier/PO management, and Reports, per defined permissions | `backend/tests/test_rbac.py::test_role_permissions_match_the_matrix`<br>`backend/tests/test_rbac.py::test_api_enforces_the_matrix_for_every_role` | Pass |
| FR5.1-UT-3 | Verify a Cashier-role user is restricted to only Sales/Returns functionality and cannot access Product/Stock/Supplier management screens | `backend/tests/test_rbac.py::test_role_permissions_match_the_matrix`<br>`backend/tests/test_rbac.py::test_api_enforces_the_matrix_for_every_role` | Pass |
| FR5.2-UT-1 | Verify a user can log in successfully with correct username and password | `backend/tests/test_auth.py::test_valid_credentials_log_in`<br>`frontend/src/modules/auth/auth.test.tsx::valid credentials open the role dashboard` | Pass |
| FR5.2-UT-2 | Verify login fails with an incorrect password and displays a generic error | `backend/tests/test_auth.py::test_invalid_credentials_get_generic_error`<br>`frontend/src/modules/auth/auth.test.tsx::invalid credentials show the generic error` | Pass |
| FR5.2-UT-3 | Verify an unauthenticated user attempting to directly access an internal application URL is redirected to the login page | `backend/tests/test_auth.py::test_every_non_public_route_requires_a_session`<br>`backend/tests/test_auth.py::test_protected_endpoint_without_session_gets_401`<br>`frontend/src/modules/auth/auth.test.tsx::an internal URL without a session shows the login page` | Pass |
| FR5.3-UT-1 | Verify a user's login event is recorded in the activity/audit log | `backend/tests/test_audit.py::test_login_is_logged_with_user_and_time` | Pass |
| FR5.3-UT-2 | Verify a data-modifying action (e.g. editing a product price) is recorded in the audit log with before/after values | `backend/tests/test_audit.py::test_price_edit_is_logged_with_old_and_new_value`<br>`frontend/src/modules/audit/audit.test.tsx::entries show who, what and when, with old and new values` | Pass |
| FR5.3-UT-3 | Verify the audit log can be filtered by a specific user to view all their activity | `backend/tests/test_audit.py::test_filter_by_user_any_case`<br>`frontend/src/modules/audit/audit.test.tsx::filtering by user shows only that user’s entries` | Pass |

### 3.6 Reporting and Analytics

| ID | Description | Evidence | Result |
|---|---|---|---|
| FR6.1-UT-1 | Verify the stock valuation report calculates total value correctly as sum of (quantity x unit cost) across all products | `backend/tests/test_reporting_stock.py::test_valuation_is_live_and_can_filter_location`<br>`backend/tests/test_reporting_stock.py::test_valuation_uses_average_cost_then_active_supplier_catalog_price` | Pass |
| FR6.1-UT-2 | Verify the report can be generated for a specific single location | `backend/tests/test_reporting_stock.py::test_valuation_is_live_and_can_filter_location`<br>`backend/tests/test_reporting_stock.py::test_valuation_uses_average_cost_then_active_supplier_catalog_price` | Pass |
| FR6.1-UT-3 | Verify the report correctly excludes products with zero stock from contributing any value, while still optionally listing them at 0 | `backend/tests/test_plan_cases.py::test_fr6_1_ut_3_zero_stock_adds_no_value` | Pass |
| FR6.2-UT-1 | Verify the sales trend report correctly ranks products by quantity sold over a selected date range | `backend/tests/test_sales_trend.py::test_fr6_2_ut_1_and_it_1_sales_trend_ranks_and_nets_returns` | Pass |
| FR6.2-UT-2 | Verify the report correctly identifies worst sellers as products with the lowest sales volume | `backend/tests/test_sales_trend.py::test_fr6_2_ut_1_and_it_1_sales_trend_ranks_and_nets_returns` | Pass |
| FR6.2-UT-3 | Verify the report can be generated for a custom date range specified by the user | `backend/tests/test_sales_trend.py::test_fr6_2_ut_3_sales_trend_rejects_invalid_ranges` | Pass |
| FR6.3-UT-1 | Verify the low-stock and reorder report lists all products currently at or below their configured reorder threshold | `backend/tests/test_reporting_stock.py::test_reorder_report_filters_thresholds_and_uses_reorder_to` | Pass |
| FR6.3-UT-2 | Verify the report suggests a reorder quantity based on the configured logic | `backend/tests/test_reporting_stock.py::test_reorder_report_filters_thresholds_and_uses_reorder_to` | Pass |
| FR6.3-UT-3 | Verify products with healthy stock (above threshold) are correctly excluded from the report | `backend/tests/test_reporting_stock.py::test_reorder_report_filters_thresholds_and_uses_reorder_to` | Pass |
| FR6.4-UT-1 | Verify the supplier performance report calculates on-time delivery rate correctly based on PO expected vs. actual receipt dates | `backend/tests/test_supplier_performance.py::test_supplier_performance_calculates_four_of_five_on_time_once_per_po` | Pass |
| FR6.4-UT-2 | Verify the report shows total order value and count of purchase orders per supplier over a selected period | `backend/tests/test_supplier_performance.py::test_supplier_performance_counts_orders_and_values_once_and_filters_by_period` | Pass |
| FR6.4-UT-3 | Verify the report can be generated to compare multiple suppliers side by side | `backend/tests/test_supplier_performance.py::test_supplier_performance_price_trends_match_supplier_and_product_history` | Pass |
| FR6.5-UT-1 | Verify any given report (e.g. Stock Valuation) can be exported successfully as a CSV file | `backend/tests/test_reporting_export.py::test_fr6_5_every_report_exports_in_both_formats`<br>`backend/tests/test_reporting_export.py::test_fr6_5_csv_matches_the_on_screen_valuation` | Pass |
| FR6.5-UT-2 | Verify any given report can be exported successfully as a PDF file | `backend/tests/test_reporting_export.py::test_fr6_5_every_report_exports_in_both_formats` | Pass |
| FR6.5-UT-3 | Verify special characters (e.g. commas, quotes in product names) are correctly escaped in CSV exports so data columns are not broken | `backend/tests/test_reporting_export.py::test_fr6_5_ut_3_commas_and_quotes_stay_in_one_cell` | Pass |

### 3.7 Search and Filter

| ID | Description | Evidence | Result |
|---|---|---|---|
| FR7.1-UT-1 | Verify searching by exact product name returns the correct matching product | `backend/tests/test_product_search.py::test_search_matches_name_sku_brand_variant_and_category` | Pass |
| FR7.1-UT-2 | Verify searching by partial product name (substring match) returns all relevant products | `backend/tests/test_product_search.py::test_search_matches_name_sku_brand_variant_and_category` | Pass |
| FR7.1-UT-3 | Verify searching by SKU returns the exact product regardless of case sensitivity | `backend/tests/test_product_search.py::test_search_matches_name_sku_brand_variant_and_category` | Pass |
| FR7.2-UT-1 | Verify products can be filtered by a specific category | `backend/tests/test_product_filters.py::test_category_and_price_range_return_exactly_the_intersection` | Pass |
| FR7.2-UT-2 | Verify products can be filtered by a price range | `backend/tests/test_product_filters.py::test_category_and_price_range_return_exactly_the_intersection` | Pass |
| FR7.2-UT-3 | Verify products can be sorted by stock level in ascending and descending order | `backend/tests/test_product_filters.py::test_price_and_stock_sorts_work_both_ways_on_live_data` | Pass |

### 3.8 Notifications

| ID | Description | Evidence | Result |
|---|---|---|---|
| FR8.1-UT-1 | Verify a low-stock website notification is generated when a product's stock crosses below its threshold | `backend/tests/test_notifications.py::test_shared_stock_updates_create_distinct_alerts_and_clear_on_recovery` | Pass |
| FR8.1-UT-2 | Verify the notification includes the product name and current stock quantity | `backend/tests/test_plan_cases.py::test_fr2_3_ut_3_and_fr8_1_ut_2_alert_only_at_or_below_threshold` | Pass |
| FR8.1-UT-3 | Verify a notification can be marked as read/dismissed by the user | `backend/tests/test_notifications.py::test_notification_feed_is_recipient_scoped_and_chronological`<br>`backend/tests/test_notifications.py::test_fr8_1_ut_3_a_notification_can_be_marked_read_and_dismissed`<br>`backend/tests/test_notifications.py::test_mark_all_read_clears_the_unread_count`<br>`frontend/src/modules/notifications/notifications.test.tsx::the panel marks a notification read and dismisses another` | Pass |
| FR8.2-UT-1 | Verify a notification is generated when a purchase order status changes to Submitted | `backend/tests/test_purchase_orders.py::test_create_list_view_edit_and_submit_po_calculates_totals_and_audits` | Pass |
| FR8.2-UT-2 | Verify a notification is generated when a purchase order status changes to Partially Received or Received | `backend/tests/test_purchase_orders.py::test_receipt_hook_advances_lifecycle_notifies_and_freezes_lines` | Pass |
| FR8.2-UT-3 | Verify a notification includes the PO number and the new status for clarity | `backend/tests/test_purchase_orders.py::test_create_list_view_edit_and_submit_po_calculates_totals_and_audits` | Pass |

### 3.9 Security

| ID | Description | Evidence | Result |
|---|---|---|---|
| SEC-AUTH-2-UT-1 | Verify a new password is stored as a salted adaptive hash | `backend/tests/test_auth.py::test_passwords_are_stored_as_salted_hashes` | Pass |
| SEC-AUTH-2-UT-2 | Verify two users with the same password get different stored hashes (salting) | `backend/tests/test_auth.py::test_passwords_are_stored_as_salted_hashes` | Pass |

## Integration test cases (86)

### 3.1 Product Management

| ID | Description | Evidence | Result |
|---|---|---|---|
| FR1.1-IT-1 | Verify that editing a product's price updates correctly across the catalog and reflects on the sales screen | `backend/tests/test_products.py::test_price_update_is_visible_to_cashier_and_audited` | Pass |
| FR1.1-IT-2 | Verify that deleting a product with zero stock removes it from catalog and stock module, but a product with existing stock cannot be deleted | `backend/tests/test_products.py::test_delete_requires_zero_stock_and_cashier_cannot_manage` | Pass |
| FR1.1-IT-3 | Verify that uploaded product images are correctly stored and retrieved when viewing a product | `backend/tests/test_plan_cases.py::test_fr1_1_it_3_uploaded_image_is_stored_and_served` | Pass |
| FR1.2-IT-1 | Verify a product assigned to a subcategory is correctly reflected in both the subcategory listing and the rolled-up parent category count/report | `backend/tests/test_categories.py::test_cycles_duplicates_delete_and_rollup_counts` | Pass |
| FR1.2-IT-2 | Verify the system blocks or warns when deleting a parent category that has active subcategories and products | `backend/tests/test_categories.py::test_cycles_duplicates_delete_and_rollup_counts` | Pass |
| FR1.2-IT-3 | Verify renaming a category updates its label everywhere it is referenced, including search/filter dropdowns | `backend/tests/test_categories.py::test_cycles_duplicates_delete_and_rollup_counts`<br>`backend/tests/test_product_search.py::test_search_matches_name_sku_brand_variant_and_category` | Pass |
| FR1.3-IT-1 | Verify each variant maintains its own independent stock count linked to the Stock Management module | `backend/tests/test_variants.py::test_variant_stock_is_independent_and_delete_is_soft` | Pass |
| FR1.3-IT-2 | Verify selecting a specific variant during a sales transaction deducts stock from the correct variant only | `backend/tests/test_sales.py::test_fr1_3_it_2_selling_a_variant_deducts_only_that_variant` | Pass |
| FR1.3-IT-3 | Verify deleting a variant does not affect other variants or the base product record | `backend/tests/test_variants.py::test_variant_stock_is_independent_and_delete_is_soft` | Pass |

### 3.2 Stock Management

| ID | Description | Evidence | Result |
|---|---|---|---|
| FR2.1-IT-1 | Verify that transferring stock between two locations updates both location balances correctly | `backend/tests/test_stock_transfers.py::test_transfer_updates_stock_movements_audit_and_valuation`<br>`backend/tests/test_stock_transfers.py::test_transfer_of_25_updates_both_balances_and_alerts` | Pass |
| FR2.1-IT-2 | Verify per-location stock feeds correctly into the multi-location stock valuation report | `backend/tests/test_stock_transfers.py::test_transfer_updates_stock_movements_audit_and_valuation`<br>`backend/tests/test_reporting_stock.py::test_valuation_is_live_and_can_filter_location` | Pass |
| FR2.1-IT-3 | Verify stock displayed at point-of-sale reflects the specific store location the cashier is logged into | `backend/tests/test_sales_availability.py::test_cashier_availability_uses_only_assigned_location` | Pass |
| FR2.2-IT-1 | Verify that a sale is rejected and stock is not deducted when attempted quantity exceeds available stock | `backend/tests/test_sales.py::test_fr2_2_it_1_sale_above_available_stock_is_rejected_and_stock_unchanged` | Pass |
| FR2.2-IT-2 | Verify partial receipt of a purchase order updates stock only for the quantity actually received, leaving the remainder pending | `backend/tests/test_purchase_order_receiving.py::test_multiple_receipts_accumulate_and_short_items_remain_outstanding`<br>`backend/tests/test_purchase_order_lifecycle.py::test_fr3_3_st_1_staff_finish_a_po_over_two_sessions` | Pass |
| FR2.2-IT-3 | Verify that stock deduction from a sale and the corresponding invoice generation happen as a single consistent operation | `backend/tests/test_sales.py::test_fr2_2_it_3_failure_after_stock_deduction_leaves_no_sale_invoice_or_stock_change` | Pass |
| FR2.3-IT-1 | Verify low-stock alerts are cleared automatically once stock is replenished above the threshold via a purchase receipt | `backend/tests/test_notifications.py::test_shared_stock_updates_create_distinct_alerts_and_clear_on_recovery` | Pass |
| FR2.3-IT-2 | Verify low-stock alerts are location-specific and do not falsely trigger based on combined multi-location stock | `backend/tests/test_notifications.py::test_alerts_are_location_scoped_and_align_with_reorder_report` | Pass |
| FR2.3-IT-3 | Verify low-stock and out-of-stock alerts appear correctly in the low-stock/reorder report so both features stay consistent | `backend/tests/test_notifications.py::test_alerts_are_location_scoped_and_align_with_reorder_report` | Pass |
| FR2.4-IT-1 | Verify manual adjustments are recorded in the immutable audit trail with user, timestamp, and reason | `backend/tests/test_stock_adjustments.py::test_negative_adjustment_reduces_stock_and_logs_reason`<br>`backend/tests/test_constraints.py::test_audit_log_is_append_only` | Pass |
| FR2.4-IT-2 | Verify a manual stock adjustment correctly feeds into the stock valuation report for the affected period | `backend/tests/test_plan_cases.py::test_fr2_4_it_2_adjustment_is_in_the_valuation_report` | Pass |
| FR2.4-IT-3 | Verify that a manual stock adjustment cannot reduce stock below zero | `backend/tests/test_stock_adjustments.py::test_adjustment_below_zero_is_blocked` | Pass |
| FR2.5-IT-1 | Verify selling a unit by serial number correctly marks that specific serial as sold and removes it from available stock, without affecting other serials | `backend/tests/test_sales.py::test_fr2_5_it_1_selling_a_serial_marks_only_that_unit_sold` | Pass |
| FR2.5-IT-2 | Verify a returned unit's batch/serial number is correctly re-added to available stock and traceable to its original sale | `backend/tests/test_returns.py::test_tracked_items_serial_and_batch_returns` | Pass |
| FR2.5-IT-3 | Verify a batch recall/lookup can retrieve all units and their sale status belonging to a specific batch | `backend/tests/test_sales.py::test_fr2_5_it_3_batch_lookup_by_number_splits_sold_and_in_stock_units`<br>`backend/tests/test_sales.py::test_batch_lookup_by_number_is_scoped_to_staff_location_and_denied_to_cashier`<br>`frontend/src/modules/stock/BatchRecallPage.test.tsx::looking up a batch number shows stock by location and the invoices it was sold on` | Pass |

### 3.3 Purchasing / Supplier Management

| ID | Description | Evidence | Result |
|---|---|---|---|
| FR3.1-IT-1 | Verify a supplier's linked product catalog is available for selection when creating a purchase order for that supplier | `backend/tests/test_purchase_orders.py::test_purchase_order_requires_active_supplier_location_and_catalog_line`<br>`frontend/src/modules/purchasing/PurchaseOrdersPage.test.tsx::creates a draft from supplier catalog prices, recalculates totals and submits it` | Pass |
| FR3.1-IT-2 | Verify deleting a supplier with open/pending purchase orders is blocked | `backend/tests/test_suppliers.py::test_supplier_deactivation_is_blocked_by_open_purchase_orders` | Pass |
| FR3.1-IT-3 | Verify editing a supplier's contact information updates correctly on existing (non-financial) purchase order references | `backend/tests/test_plan_cases.py::test_fr3_1_it_3_supplier_edit_shows_on_existing_purchase_order`<br>`backend/tests/test_suppliers.py::test_supplier_deactivation_preserves_purchase_order_prices_and_history` | Pass |
| FR3.2-IT-1 | Verify a submitted PO status transitions correctly (Draft to Submitted to Partially Received to Received) as receipt actions occur | `backend/tests/test_purchase_orders.py::test_receipt_hook_advances_lifecycle_notifies_and_freezes_lines` | Pass |
| FR3.2-IT-2 | Verify a PO cannot be edited once it has moved past Draft/Submitted status (after any receipt has occurred) | `backend/tests/test_purchase_orders.py::test_receipt_hook_advances_lifecycle_notifies_and_freezes_lines` | Pass |
| FR3.2-IT-3 | Verify cancelling a PO before any receipt correctly sets status to Cancelled and excludes it from pending-order reports | `backend/tests/test_purchase_orders.py::test_cancelled_orders_are_excluded_from_pending_orders` | Pass |
| FR3.3-IT-1 | Verify receiving stock against a PO correctly updates stock at the specific receiving location specified on the PO | `backend/tests/test_purchase_order_lifecycle.py::test_fr3_3_it_1_receipt_adds_stock_only_at_the_po_receiving_location` | Pass |
| FR3.3-IT-2 | Verify a completed receipt transaction is correctly reflected in the supplier's pricing history | `backend/tests/test_supplier_price_history.py::test_receipts_append_price_history_and_filters_keep_supplier_attribution`<br>`backend/tests/test_purchase_order_receiving.py::test_full_receipt_updates_stock_cost_history_audit_and_status_notifications` | Pass |
| FR3.3-IT-3 | Verify receiving stock with damaged/short quantities can be recorded with a discrepancy note, separate from the accepted quantity | `backend/tests/test_purchase_order_receiving.py::test_multiple_receipts_accumulate_and_short_items_remain_outstanding`<br>`backend/tests/test_purchase_order_receiving.py::test_receipt_integrates_batch_and_serial_tracking` | Pass |
| FR3.4-IT-1 | Verify pricing history data correctly feeds into the Supplier Performance Report, e.g. price trend/variance | `backend/tests/test_supplier_performance.py::test_supplier_performance_price_trends_match_supplier_and_product_history` | Pass |
| FR3.4-IT-2 | Verify pricing history entries are immutable (cannot be edited/deleted) once recorded, preserving historical accuracy | `backend/tests/test_supplier_price_history.py::test_supplier_price_history_is_read_only_and_manager_admin_only`<br>`backend/tests/test_constraints.py::test_supplier_price_history_is_append_only` | Pass |
| FR3.4-IT-3 | Verify pricing history correctly distinguishes entries by supplier when the same product is sourced from multiple suppliers at different prices | `backend/tests/test_supplier_price_history.py::test_receipts_append_price_history_and_filters_keep_supplier_attribution` | Pass |

### 3.4 Sales / Orders

| ID | Description | Evidence | Result |
|---|---|---|---|
| FR4.1-IT-1 | Verify a multi-item sale correctly deducts stock for each item independently and calculates the correct total | `backend/tests/test_sales.py::test_fr4_1_it_1_multi_item_sale_deducts_each_item_and_totals_both` | Pass |
| FR4.1-IT-2 | Verify two concurrent sales for the same last unit of a product do not both succeed (no overselling) | `backend/tests/test_sales.py::test_fr4_1_it_2_two_concurrent_sales_of_the_last_unit_sell_it_once`<br>`backend/tests/test_batch_serial_tracking.py::test_concurrent_tracked_sales_cannot_sell_last_unit_twice` | Pass |
| FR4.1-IT-3 | Verify a completed sale transaction correctly feeds into the sales trend report for the current day | `backend/tests/test_sales_trend.py::test_fr6_2_ut_1_and_it_1_sales_trend_ranks_and_nets_returns` | Pass |
| FR4.2-IT-1 | Verify a return of a damaged/defective item is flagged and NOT automatically restocked as sellable | `backend/tests/test_returns.py::test_fr4_2_it_1_damaged_line_not_restocked_and_mixed_return`<br>`backend/tests/test_constraints.py::test_damaged_return_cannot_be_restocked` | Pass |
| FR4.2-IT-2 | Verify a return for a sale older than 30 days requires Manager approval at the till | `backend/tests/test_returns.py::test_fr4_2_it_2_late_return_manager_override_and_lockout` | Pass |
| FR4.2-IT-3 | Verify a processed return correctly reduces the reported sales figures in the sales trend report for that period | `backend/tests/test_returns.py::test_fr4_2_it_3_net_sales_data_aggregatable`<br>`backend/tests/test_sales_trend.py::test_fr6_2_ut_1_and_it_1_sales_trend_ranks_and_nets_returns` | Pass |
| FR4.3-IT-1 | Verify the invoice can be reprinted/re-viewed later from the sales transaction history without altering original data | `backend/tests/test_invoices.py::test_fr4_3_it_1_reprint_after_catalog_edits_matches_the_original`<br>`backend/tests/test_invoices.py::test_fr4_3_it_1_invoice_row_rejects_updates` | Pass |
| FR4.3-IT-2 | Verify an invoice linked to a later-processed return correctly shows an updated status without altering the original transaction record | `backend/tests/test_invoices.py::test_fr4_3_it_2_partial_return_annotates_the_invoice_without_changing_the_records` | Pass |
| FR4.3-IT-3 | Verify invoice records are retained and retrievable per the data retention/compliance requirement | `backend/tests/test_invoices.py::test_fr4_3_it_3_history_finds_a_seven_year_old_sale_by_date_and_number`<br>`backend/tests/test_invoices.py::test_fr4_3_it_3_invoice_near_the_end_of_retention_is_retrievable_in_full`<br>`backend/tests/test_retention.py::test_retention_archive_dry_run_then_execute_is_verified_and_repeatable` | Pass |

### 3.5 User Management

| ID | Description | Evidence | Result |
|---|---|---|---|
| FR5.1-IT-1 | Verify changing a user's role immediately updates their accessible functionality without requiring account recreation | `backend/tests/test_rbac.py::test_role_change_applies_to_the_next_request`<br>`backend/tests/test_users.py::test_role_change_applies_on_the_next_request` | Pass |
| FR5.1-IT-2 | Verify role-based restrictions are enforced at the backend/API level, not just hidden in the UI | `backend/tests/test_rbac.py::test_api_enforces_the_matrix_for_every_role` | Pass |
| FR5.1-IT-3 | Verify a user assigned to Staff correctly sees exactly the permitted menu options matching their exact role definition | `backend/tests/test_rbac.py::test_me_lists_the_role_permissions`<br>`frontend/src/shell/shell.test.tsx::the %s menu shows exactly its items` | Pass |
| FR5.2-IT-1 | Verify a session expires after a defined period of inactivity and requires re-authentication | `backend/tests/test_auth.py::test_idle_session_expires`<br>`frontend/src/modules/auth/auth.test.tsx::a request rejected for an expired session sends the user to log in` | Pass |
| FR5.2-IT-2 | Verify that authorization checks are applied per individual action even within a screen the role can otherwise access | `backend/tests/test_rbac.py::test_per_action_check_within_a_screen` | Pass |
| FR5.2-IT-3 | Verify passwords are stored as salted one-way hashes and not retrievable in plain text, including via password-reset flows | `backend/tests/test_auth.py::test_passwords_are_stored_as_salted_hashes`<br>`backend/tests/test_auth.py::test_password_reset_flow` | Pass |
| FR5.3-IT-1 | Verify audit log entries are generated consistently across different modules (stock adjustment, PO, sales, user management) using the same log structure | `backend/tests/test_audit.py::test_entries_from_every_module_share_one_structure` | Pass |
| FR5.3-IT-2 | Verify the audit log is immutable - entries cannot be edited or deleted by any user, including Admin | `backend/tests/test_audit.py::test_api_has_no_way_to_change_entries`<br>`backend/tests/test_audit.py::test_admin_cannot_edit_or_delete_an_entry`<br>`backend/tests/test_audit.py::test_database_rejects_changes_made_through_the_orm` | Pass |
| FR5.3-IT-3 | Verify audit log entries correctly capture failed/denied authorization attempts | `backend/tests/test_rbac.py::test_denied_attempt_is_audited` | Pass |

### 3.6 Reporting and Analytics

| ID | Description | Evidence | Result |
|---|---|---|---|
| FR6.1-IT-1 | Verify a manual stock adjustment is reflected in the stock valuation report generated immediately afterward | `backend/tests/test_plan_cases.py::test_fr2_4_it_2_adjustment_is_in_the_valuation_report` | Pass |
| FR6.1-IT-2 | Verify the report can be exported to both CSV and PDF formats with identical underlying data | `backend/tests/test_reporting_export.py::test_fr6_1_it_2_valuation_csv_and_pdf_carry_the_same_data_as_the_screen` | Pass |
| FR6.1-IT-3 | Verify the report correctly aggregates value across all locations when no location filter is applied | `backend/tests/test_reporting_stock.py::test_valuation_is_live_and_can_filter_location` | Pass |
| FR6.2-IT-1 | Verify a processed return correctly reduces the net sales figures used in the trend calculation | `backend/tests/test_sales_trend.py::test_fr6_2_ut_1_and_it_1_sales_trend_ranks_and_nets_returns` | Pass |
| FR6.2-IT-2 | Verify the report aggregates sales data consistently across multiple store locations when no location filter is applied | `backend/tests/test_sales_trend.py::test_fr6_2_it_2_unfiltered_report_is_the_sum_of_both_locations` | Pass |
| FR6.2-IT-3 | Verify the report can be exported in CSV and PDF formats and matches on-screen data | `backend/tests/test_sales_trend.py::test_fr6_2_it_3_csv_and_pdf_exports_match_the_on_screen_ranking` | Pass |
| FR6.3-IT-1 | Verify the report updates correctly after a purchase order is received and stock rises above threshold | `backend/tests/test_purchase_order_receiving.py::test_multiple_receipts_accumulate_and_short_items_remain_outstanding` | Pass |
| FR6.3-IT-2 | Verify the report is consistent with the low-stock alerts shown elsewhere in the system | `backend/tests/test_notifications.py::test_alerts_are_location_scoped_and_align_with_reorder_report` | Pass |
| FR6.3-IT-3 | Verify the report can be filtered by location to show reorder needs for a specific store/warehouse only | `backend/tests/test_reporting_stock.py::test_reorder_report_filters_thresholds_and_uses_reorder_to` | Pass |
| FR6.4-IT-1 | Verify partial/short receipts are correctly factored into the supplier's fulfillment-accuracy metric | `backend/tests/test_supplier_performance.py::test_supplier_performance_uses_only_accepted_receipts_and_reflects_receipt_updates` | Pass |
| FR6.4-IT-2 | Verify the report correctly reflects pricing trend data from the supplier pricing history | `backend/tests/test_supplier_performance.py::test_supplier_performance_price_trends_match_supplier_and_product_history` | Pass |
| FR6.4-IT-3 | Verify the report can be exported in CSV and PDF and matches the on-screen data | `backend/tests/test_supplier_performance.py::test_supplier_performance_uses_only_accepted_receipts_and_reflects_receipt_updates`<br>`backend/tests/test_supplier_performance.py::test_supplier_performance_counts_orders_and_values_once_and_filters_by_period` | Pass |
| FR6.5-IT-1 | Verify export functionality works consistently for all report types available in the system | `backend/tests/test_reporting_export.py::test_fr6_5_every_report_exports_in_both_formats`<br>`backend/tests/test_reporting_export.py::test_supplier_performance_export_matches_the_on_screen_report` | Pass |
| FR6.5-IT-2 | Verify exported PDF reports include a header with report title, generation date, and applied filters for traceability | `backend/tests/test_reporting_export.py::test_fr6_5_it_2_pdf_header_has_title_time_and_filter` | Pass |
| FR6.5-IT-3 | Verify a large report (5000+ rows) exports successfully without truncation or timeout | `backend/tests/test_reporting_export.py::test_fr6_5_it_3_five_thousand_rows_export_without_truncation` | Pass |

### 3.7 Search and Filter

| ID | Description | Evidence | Result |
|---|---|---|---|
| FR7.1-IT-1 | Verify search results correctly reflect real-time stock and price data from the Stock and Product modules | `backend/tests/test_product_search.py::test_search_is_literal_live_and_location_scoped` | Pass |
| FR7.1-IT-2 | Verify searching by category name returns all products under that category, including subcategories | `backend/tests/test_product_search.py::test_search_matches_name_sku_brand_variant_and_category` | Pass |
| FR7.1-IT-3 | Verify a search with no matching results displays an appropriate empty-state message rather than an error | `backend/tests/test_product_search.py::test_search_matches_name_sku_brand_variant_and_category` | Pass |
| FR7.2-IT-1 | Verify combining a category filter with a price-range filter returns the correct intersection of results | `backend/tests/test_product_filters.py::test_category_and_price_range_return_exactly_the_intersection` | Pass |
| FR7.2-IT-2 | Verify sorting by price correctly reflects the most recently updated price values from the Product module | `backend/tests/test_product_filters.py::test_price_and_stock_sorts_work_both_ways_on_live_data` | Pass |
| FR7.2-IT-3 | Verify filtering by stock level correctly reflects real-time stock data | `backend/tests/test_product_filters.py::test_stock_status_filter_is_scoped_to_the_users_location` | Pass |

### 3.8 Notifications

| ID | Description | Evidence | Result |
|---|---|---|---|
| FR8.1-IT-1 | Verify a website low-stock notification is generated consistently with the corresponding stock alert and appears in the same reporting cycle | `backend/tests/test_notifications.py::test_alerts_are_location_scoped_and_align_with_reorder_report` | Pass |
| FR8.1-IT-2 | Verify notifications are scoped per user's assigned location, so a Staff member at Store-A does not see low-stock notifications for Store-B | `backend/tests/test_notifications.py::test_alerts_are_location_scoped_and_align_with_reorder_report` | Pass |
| FR8.1-IT-3 | Verify multiple simultaneous low-stock events each generate a distinct notification without merging or dropping any | `backend/tests/test_notifications.py::test_shared_stock_updates_create_distinct_alerts_and_clear_on_recovery` | Pass |
| FR8.2-IT-1 | Verify order status notifications are routed to the Manager who created the PO and to Admin, not to other users | `backend/tests/test_purchase_orders.py::test_admin_creator_is_notified_of_po_status_changes` | Pass |
| FR8.2-IT-2 | Verify a PO cancellation correctly triggers a corresponding Cancelled status notification | `backend/tests/test_purchase_orders.py::test_cancelled_orders_are_excluded_from_pending_orders` | Pass |
| FR8.2-IT-3 | Verify order status notifications are timestamped accurately and appear in correct chronological order alongside other notifications | `backend/tests/test_purchase_order_lifecycle.py::test_fr8_2_it_3_status_changes_across_pos_are_listed_in_event_order`<br>`backend/tests/test_notifications.py::test_notification_feed_is_recipient_scoped_and_chronological` | Pass |

### 3.9 Security

| ID | Description | Evidence | Result |
|---|---|---|---|
| SEC-INP-2-IT-1 | Verify product search is not vulnerable to SQL injection | `backend/tests/test_plan_cases.py::test_sec_inp_2_it_1_search_is_not_injectable`<br>`backend/tests/test_product_search.py::test_search_is_literal_live_and_location_scoped` | Pass |
| SEC-INP-2-IT-2 | Verify filter and sort parameters sent directly to the API are not injectable | `backend/tests/test_plan_cases.py::test_sec_inp_2_it_2_filter_and_sort_parameters_are_not_injectable` | Pass |
| SEC-INP-3-IT-1 | Verify a script in a product name is displayed as text, not executed | `backend/tests/test_plan_cases.py::test_sec_inp_3_it_1_script_in_product_name_is_returned_as_data`<br>`frontend/src/security.test.tsx::the product list shows a script name literally`<br>`frontend/src/security.test.tsx::search results show a script name literally`<br>`frontend/src/security.test.tsx::the sales screen shows a script name literally in results and the cart` | Pass |
| SEC-SES-4-IT-1 | Verify a state-changing request without a valid CSRF token is rejected | `backend/tests/test_csrf.py::test_sec_ses_4_it_1_request_without_token_is_rejected` | Pass |
| SEC-SES-4-IT-2 | Verify normal in-app requests carrying a valid CSRF token succeed | `backend/tests/test_csrf.py::test_sec_ses_4_it_2_request_with_token_succeeds`<br>`frontend/src/api.test.ts` | Pass |
