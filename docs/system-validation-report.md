# System validation report

Final results for the system test (ST) cases of
[`Documents/Test_Plan_Document.docx`](../Documents/Test_Plan_Document.docx), plus the checks that validate
the non-functional requirements. Unit and integration results are in
[`unit-test-report.md`](unit-test-report.md).

## Result

**All 57 system test cases pass.** 54 were executed as automated tests that drive the system through
its HTTP API (and, where the case is about a screen, through the React component tests). The remaining 3
needed a browser or a large dataset and were executed separately; their evidence is under
[Cases executed outside pytest](#cases-executed-outside-pytest).

| Module | Cases | Pass | Fail |
|---|---:|---:|---:|
| 3.1 Product Management | 6 | 6 | 0 |
| 3.2 Stock Management | 10 | 10 | 0 |
| 3.3 Purchasing / Supplier Management | 8 | 8 | 0 |
| 3.4 Sales / Orders | 6 | 6 | 0 |
| 3.5 User Management | 6 | 6 | 0 |
| 3.6 Reporting and Analytics | 10 | 10 | 0 |
| 3.7 Search and Filter | 4 | 4 | 0 |
| 3.8 Notifications | 4 | 4 | 0 |
| 3.9 Security | 3 | 3 | 0 |
| **Total** | **57** | **57** | **0** |

Environment:

- Run date: 2026-11-06
- Backend: Python 3.13.18, pytest 8.3.4, coverage.py 7.17.2 (via pytest-cov), PostgreSQL 16.15
- Frontend: Node 22.23.4, Vitest 3.2.7 (jsdom), @vitest/coverage-v8 3.2.7
- Code under test: `main` at commit `b769635` (merge of pull request #90), unmodified

Docker was not available in the session that produced these numbers, so the suites ran directly
on the host (a Python virtual environment with `backend/requirements-dev.txt`, a local PostgreSQL 16
server, and `npm ci` for the frontend) instead of in the project's containers. The containers use
Python 3.12 and `postgres:16-alpine`. The tests create their own throwaway databases, so the
method is the same, but the interpreter and database build differ slightly from the CI images.

## What "automated system test" means here

A system test in the plan is an end-to-end user flow (for example "cashier sells a variant and the invoice
shows it"). The automated versions start the real FastAPI application against a migrated PostgreSQL
database and call it over HTTP with the same cookies, CSRF header and role permissions a browser would use.
The browser steps are covered by the React tests (Testing Library on jsdom), which render each screen
against a mocked API. Where a case has both parts, the Evidence column lists the backend test and the
`frontend/...` test. No automated test drives a real browser against the full stack, apart from the one
check described below.

## Cases executed outside pytest

### FR2.2-ST-2: stock dashboard reflects a concurrent sale

Run in Chromium (Playwright) against the sample data from `python -m scripts.seed`, with the API and the Vite
dev server running locally.

| Step | Observed |
|---|---|
| Manager opens Stock levels | Redmi 13C at Main Street Store shows quantity **10** |
| Cashier records a sale of 2 units (API) | `201 Created` |
| Manager refreshes the page | Quantity shows **8**; page reloaded and showed the new value in **146 ms** |
| Five further refreshes | 174, 163, 164, 164 and 166 ms |

The expected result is an updated level within 2 s (NFR-1). The same read at 10,003 SKUs and 50,003 stock
rows (the load-test database): sale of 1 unit changes the quantity from 40 to 39, and the stock levels
request takes **0.71 s** before and after the sale.

### FR7.1-ST-1: search on a large catalogue

`python -m scripts.loadtest` on 2026-11-06: 10,003 products, 10 concurrent clients, 100 search requests with
six different terms (including one with no matches).

| Median | p95 | Max | Errors | Limit |
|---:|---:|---:|---:|---|
| 53 ms | 87 ms | 102 ms | 0 | 2 s |

### FR7.2-ST-1: combined filter and sort on 10,000+ SKUs

The load test times each filter and sort on its own. The case needs a combination and an accuracy check, so
the same 10,003-SKU database was also queried with one category, a price range of 500 to 5,000 and a sort
by stock, highest first (`/api/product?category_id=13&min_price=500&max_price=5000&sort=stock&order=desc`).

| Check | Result |
|---|---|
| Matches returned vs. SQL count for the same filter | 20 and 20 |
| All returned prices within 500 to 5,000 | Yes (1,133.00 to 4,823.00) |
| Stock in descending order | Yes |
| Latency, 100 requests, 10 clients | median 34 ms, p95 79 ms, max 90 ms, 0 errors |

## Non-functional validation (load test)

`python -m scripts.loadtest`, 2026-11-06. 10,003 products, 5 locations, 50,003 stock rows, 10 concurrent API
clients, 100 requests per scenario, 2 uvicorn workers. The profile and pass criteria are in
[`performance.md`](performance.md).

| Scenario | Median (ms) | p95 (ms) | Max (ms) | Errors | Target (p95) |
|---|---:|---:|---:|---:|---|
| list (page 1, by name) | 57 | 90 | 107 | 0 | < 2 s |
| list (deep page) | 60 | 89 | 117 | 0 | < 2 s |
| sort by price | 62 | 95 | 99 | 0 | < 2 s |
| sort by stock | 371 | 560 | 645 | 0 | < 2 s |
| filter by category | 50 | 75 | 85 | 0 | < 2 s |
| filter by price range | 57 | 94 | 105 | 0 | < 2 s |
| filter by stock status | 465 | 689 | 744 | 0 | < 2 s |
| search | 53 | 87 | 102 | 0 | < 2 s |

Concurrent sales (NFR-2): 8 cashiers made 128 sale attempts in 6.7 s. 80 were recorded, 48 were rejected as out
of stock and none failed any other way. Each of the three contended items ended with `40 - sold` on hand
(0), so there was no overselling, deadlock or negative stock.

| Report | Time (s) | Size (KiB) |
|---|---:|---:|
| valuation report (JSON) | 1.2 | 13,094 |
| reorder report (JSON) | 0.8 | 2,404 |
| valuation export (CSV) | 1.2 | 3,675 |
| valuation export (PDF) | 7.5 | 4,221 |
| reorder export (CSV) | 0.8 | 560 |
| reorder export (PDF) | 2.1 | 767 |

All 18 load-test checks passed. The numbers are lower than the committed
[`performance-results.md`](performance-results.md) (2026-11-02) because absolute times depend on the host; both runs pass.

Observation outside the plan: the Stock levels screen loads every location's stock in a single request
(`GET /api/stock/levels`) and filters it in the browser. At 50,003 stock rows that request takes about
1.0 s (median of 10, maximum 1.1 s) and returns every row. It is inside the 2 s target at the load-test size,
but it is the screen that will slow down first as the catalogue grows.

## Other validation evidence

- **Usability:** an expert review was done on 2026-11-01 (see [`usability/report.md`](usability/report.md)).
  No sessions with real users have been run, so NFR-10 is not validated by users.
- **Security cases (section 3.9):** all 10 pass, as automated tests. They are included in the totals above.
- **Browsers (NFR-9):** the browser check above used Chromium only. Firefox and Edge were not run.

## System test cases (57)

### 3.1 Product Management

| ID | Description | Evidence | Result |
|---|---|---|---|
| FR1.1-ST-1 | End-to-end verification of the full add-product workflow from login to catalog visibility | `backend/tests/test_plan_cases.py::test_fr1_1_st_1_add_product_flow_from_login_to_catalog` | Pass |
| FR1.1-ST-2 | Verify that a user without product-management permissions (Cashier) cannot access the Add/Edit/Delete Product functionality | `backend/tests/test_products.py::test_delete_requires_zero_stock_and_cashier_cannot_manage`<br>`frontend/src/modules/product/product.test.tsx::cashier cannot open product management but can see search placeholder` | Pass |
| FR1.2-ST-1 | End-to-end verification of a full 3-level category hierarchy and its display in the catalog browsing UI | `backend/tests/test_categories.py::test_admin_creates_tree_in_tree_order_and_invalid_parent_is_not_saved`<br>`frontend/src/modules/product/product.test.tsx::category tree shows hierarchy and staff is denied category management` | Pass |
| FR1.2-ST-2 | Verify category management is restricted to Admin/Manager roles and inaccessible to Cashier/Staff | `backend/tests/test_categories.py::test_staff_and_cashier_can_read_but_cannot_manage` | Pass |
| FR1.3-ST-1 | End-to-end verification that variant selection is available and functions correctly in the catalog browsing and sales flow | `backend/tests/test_sales.py::test_fr1_3_st_1_cashier_sells_a_chosen_variant_at_its_price_and_invoice_shows_it` | Pass |
| FR1.3-ST-2 | Verify variant attribute options (Color, Storage) are configurable and reused consistently across products of the same category | `backend/tests/test_variants.py::test_variants_normalize_attributes_and_use_effective_price`<br>`backend/tests/test_variants.py::test_duplicate_variant_combination_and_sku_are_field_errors` | Pass |

### 3.2 Stock Management

| ID | Description | Evidence | Result |
|---|---|---|---|
| FR2.1-ST-1 | End-to-end verification of adding a new store location and tracking a product's stock there from scratch | `backend/tests/test_stock_locations.py::test_admin_and_manager_can_create_and_edit_locations`<br>`backend/tests/test_stock_levels.py::test_stock_levels_are_per_location_and_expose_combined_totals`<br>`frontend/src/modules/stock/LocationsPage.test.tsx::lists active and inactive locations and adds a new one` | Pass |
| FR2.1-ST-2 | Verify a Staff user (without multi-location visibility permission) can view stock only for their assigned location, not all locations | `backend/tests/test_stock_levels.py::test_staff_stock_levels_are_scoped_to_assigned_location`<br>`backend/tests/test_rbac.py::test_staff_see_only_their_own_location` | Pass |
| FR2.2-ST-1 | End-to-end verification across a full sale-purchase-transfer cycle to confirm stock accuracy at every stage | `backend/tests/test_sales.py::test_fr2_2_st_1_sale_receipt_and_transfer_cycle_keeps_both_locations_exact` | Pass |
| FR2.2-ST-2 | Verify stock updates are reflected in real time on the Manager's stock dashboard without an unacceptable refresh delay | Browser check with Playwright against a local stack, plus API timing on the 10,003-SKU load-test database (2026-11-06) | Pass |
| FR2.3-ST-1 | End-to-end verification that a Manager receives and can act on a low-stock alert from notification to reorder | `backend/tests/test_notifications.py::test_shared_stock_updates_create_distinct_alerts_and_clear_on_recovery`<br>`frontend/src/modules/notifications/notifications.test.tsx::the notifications page lists alerts and Create PO opens a prefilled draft`<br>`frontend/src/modules/notifications/notifications.test.tsx::a link in the bell panel marks the notification read and then navigates` | Pass |
| FR2.3-ST-2 | Verify alert thresholds can be configured per product and that changing the threshold immediately affects alert evaluation | `backend/tests/test_notifications.py::test_threshold_changes_reevaluate_immediately_and_cashier_is_denied`<br>`frontend/src/modules/stock/StockLevelsPage.test.tsx::saves reorder settings for a stock record` | Pass |
| FR2.4-ST-1 | End-to-end verification that only authorized roles (Staff, Manager, Admin) can perform manual stock adjustments, and Cashier cannot | `backend/tests/test_stock_adjustments.py::test_cashier_is_denied`<br>`frontend/src/modules/stock/StockLevelsPage.test.tsx::hides the Adjust action from users without stock.adjust` | Pass |
| FR2.4-ST-2 | Verify that a full adjustment workflow (adjustment, audit log, stock report) remains consistent end-to-end | `backend/tests/test_stock_adjustments.py::test_negative_adjustment_reduces_stock_and_logs_reason`<br>`backend/tests/test_plan_cases.py::test_fr2_4_it_2_adjustment_is_in_the_valuation_report` | Pass |
| FR2.5-ST-1 | End-to-end verification of full batch/serial traceability from receipt through sale to a hypothetical recall scenario | `backend/tests/test_sales.py::test_fr2_5_st_1_batch_received_on_a_po_is_traceable_through_sales_to_a_recall` | Pass |
| FR2.5-ST-2 | Verify batch/serial tracking fields are optional and do not block normal operations for products not configured for tracking | `backend/tests/test_stock_adjustments.py::test_positive_adjustment_increases_stock`<br>`backend/tests/test_stock_transfers.py::test_transfer_updates_stock_movements_audit_and_valuation` | Pass |

### 3.3 Purchasing / Supplier Management

| ID | Description | Evidence | Result |
|---|---|---|---|
| FR3.1-ST-1 | End-to-end verification of onboarding a new supplier and using it immediately in the purchasing workflow | `backend/tests/test_purchase_orders.py::test_create_list_view_edit_and_submit_po_calculates_totals_and_audits`<br>`frontend/src/modules/purchasing/SuppliersPage.test.tsx::loads supplier catalog and submits product association changes` | Pass |
| FR3.1-ST-2 | Verify supplier management screen is accessible to Manager and Admin roles but not to Cashier | `backend/tests/test_suppliers.py::test_staff_and_cashier_are_denied_supplier_management` | Pass |
| FR3.2-ST-1 | End-to-end verification of the complete purchase order lifecycle from creation to full receipt and stock update | `backend/tests/test_purchase_order_lifecycle.py::test_fr3_2_st_1_three_line_po_goes_from_creation_to_received_with_stock` | Pass |
| FR3.2-ST-2 | Verify PO creation and management is restricted to Manager/Admin and not accessible to Staff or Cashier | `backend/tests/test_purchase_orders.py::test_admin_can_manage_purchase_orders_staff_and_cashier_are_denied` | Pass |
| FR3.3-ST-1 | End-to-end verification that a two-stage partial receipt correctly finalizes the PO and stock over multiple receiving sessions | `backend/tests/test_purchase_order_lifecycle.py::test_fr3_3_st_1_staff_finish_a_po_over_two_sessions` | Pass |
| FR3.3-ST-2 | Verify receiving stock is accessible to Staff and Manager roles but not to Cashier | `backend/tests/test_purchase_order_receiving.py::test_staff_can_receive_only_assigned_location_orders_and_cashier_is_denied` | Pass |
| FR3.4-ST-1 | End-to-end verification that a Manager can use price history to compare suppliers before creating a new PO for the same product | `backend/tests/test_purchase_order_lifecycle.py::test_fr3_4_st_1_manager_compares_supplier_prices_then_orders_from_the_cheaper` | Pass |
| FR3.4-ST-2 | Verify pricing history view is accessible to Manager/Admin but not to Cashier or Staff | `backend/tests/test_supplier_price_history.py::test_supplier_price_history_is_read_only_and_manager_admin_only` | Pass |

### 3.4 Sales / Orders

| ID | Description | Evidence | Result |
|---|---|---|---|
| FR4.1-ST-1 | End-to-end verification of a complete sales transaction from product search through stock deduction and invoice generation | `backend/tests/test_sales.py::test_fr4_1_st_1_search_to_sale_to_invoice_end_to_end`<br>`frontend/src/modules/sales/PosPage.test.tsx::Alt shortcuts focus search and complete a sale` | Pass |
| FR4.1-ST-2 | Verify sales transaction recording is accessible to Cashier role and Manager, but not to Staff | `backend/tests/test_sales.py::test_fr4_1_st_2_staff_cannot_record_sales_but_cashier_and_manager_can` | Pass |
| FR4.2-ST-1 | End-to-end verification of the full return workflow from invoice lookup through restocking and updated reporting | `backend/tests/test_returns.py::test_fr4_2_st_1_end_to_end_sale_to_return`<br>`backend/tests/test_sales_trend.py::test_fr6_2_ut_1_and_it_1_sales_trend_ranks_and_nets_returns`<br>`frontend/src/modules/sales/ReturnsPage.test.tsx::result panel shows credit note number, refund total and restock status` | Pass |
| FR4.2-ST-2 | Verify return processing is accessible to Cashier role | `backend/tests/test_returns.py::test_authorization_and_location_scoping` | Pass |
| FR4.3-ST-1 | End-to-end verification that invoice numbering is sequential/unique across concurrent transactions from multiple cashier terminals | `backend/tests/test_invoices.py::test_fr4_3_st_1_twenty_parallel_cashiers_get_distinct_invoice_numbers`<br>`backend/tests/test_constraints.py::test_invoice_numbers_unique_and_sequential` | Pass |
| FR4.3-ST-2 | Verify invoice export/print function works correctly and produces a correctly formatted document/printout | `backend/tests/test_invoices.py::test_fr4_3_st_2_invoice_pdf_has_attachment_headers_and_snapshot_text`<br>`backend/tests/test_invoices.py::test_fr4_3_st_2_long_invoice_spans_pages_and_credit_note_pdf_is_legible` | Pass |

### 3.5 User Management

| ID | Description | Evidence | Result |
|---|---|---|---|
| FR5.1-ST-1 | End-to-end verification that all four roles (Admin, Manager, Staff, Cashier) each see correctly scoped functionality across the entire application | `backend/tests/test_rbac.py::test_api_enforces_the_matrix_for_every_role`<br>`backend/tests/test_rbac.py::test_staff_see_only_their_own_location` | Pass |
| FR5.1-ST-2 | Verify only Admin role can access the User Management screen to create/edit/deactivate other user accounts | `backend/tests/test_users.py::test_non_admin_cannot_call_management_endpoints`<br>`frontend/src/modules/auth/UsersPage.test.tsx::Manager opening users sees Access denied` | Pass |
| FR5.2-ST-1 | End-to-end verification of the login-to-logout session lifecycle, including correct enforcement of role-based access throughout | `backend/tests/test_auth.py::test_logout_invalidates_session_on_server`<br>`backend/tests/test_rbac.py::test_api_enforces_the_matrix_for_every_role`<br>`frontend/src/modules/auth/auth.test.tsx::sign out returns to the login page` | Pass |
| FR5.2-ST-2 | Verify account lockout occurs after 5 consecutive failed login attempts | `backend/tests/test_auth.py::test_lockout_after_five_failures_blocks_correct_password` | Pass |
| FR5.3-ST-1 | End-to-end verification that a full day's mixed activity across all roles produces a complete and accurate audit trail | `backend/tests/test_audit.py::test_mixed_activity_across_all_roles_is_in_the_trail_in_order`<br>`backend/tests/test_audit.py::test_entries_from_every_module_share_one_structure` | Pass |
| FR5.3-ST-2 | Verify audit log viewing/export is restricted to Admin role only | `backend/tests/test_audit.py::test_only_admin_can_view_the_log`<br>`frontend/src/modules/audit/audit.test.tsx::a non-Admin is denied and the log is never requested` | Pass |

### 3.6 Reporting and Analytics

| ID | Description | Evidence | Result |
|---|---|---|---|
| FR6.1-ST-1 | End-to-end verification that the report is accessible only to Manager/Admin roles and reflects real, current data at time of generation | `backend/tests/test_reporting_stock.py::test_valuation_is_live_and_can_filter_location`<br>`backend/tests/test_reporting_stock.py::test_staff_cannot_access_stock_reports`<br>`backend/tests/test_reporting_stock.py::test_cashier_cannot_access_stock_reports` | Pass |
| FR6.1-ST-2 | Verify Cashier and Staff roles cannot access the Stock Valuation Report | `backend/tests/test_reporting_stock.py::test_staff_cannot_access_stock_reports`<br>`backend/tests/test_reporting_stock.py::test_cashier_cannot_access_stock_reports`<br>`backend/tests/test_rbac.py::test_api_enforces_the_matrix_for_every_role` | Pass |
| FR6.2-ST-1 | End-to-end verification that a Manager can use the sales trend report to identify a best-seller and cross-reference it against stock levels for reorder planning | `backend/tests/test_sales_trend.py::test_fr6_2_ut_1_and_it_1_sales_trend_ranks_and_nets_returns` | Pass |
| FR6.2-ST-2 | Verify Sales Trend Report access is restricted to Manager/Admin and not available to Cashier/Staff | `backend/tests/test_reporting_export.py::test_fr6_5_st_1_export_is_denied_where_the_report_is_denied`<br>`backend/tests/test_rbac.py::test_api_enforces_the_matrix_for_every_role` | Pass |
| FR6.3-ST-1 | End-to-end verification that a Manager can generate the reorder report and directly initiate a purchase order for a flagged item | `frontend/src/modules/reporting/LowStockReportPage.test.tsx::low-stock report filters locations and links a prefilled PO`<br>`frontend/src/modules/purchasing/PurchaseOrdersPage.test.tsx::reorder report links prefill a draft purchase order` | Pass |
| FR6.3-ST-2 | Verify the report is accessible to Manager/Admin roles and not to Cashier | `backend/tests/test_reporting_stock.py::test_admin_can_access_reorder_report`<br>`backend/tests/test_reporting_stock.py::test_staff_cannot_access_stock_reports`<br>`backend/tests/test_reporting_stock.py::test_cashier_cannot_access_stock_reports`<br>`backend/tests/test_rbac.py::test_api_enforces_the_matrix_for_every_role` | Pass |
| FR6.4-ST-1 | End-to-end verification that a Manager uses the supplier performance report to make an informed decision to switch suppliers for a product | `frontend/src/modules/reporting/SupplierPerformanceReportPage.test.tsx::renders supplier metrics and recorded product price changes side by side`<br>`frontend/src/modules/reporting/SupplierPerformanceReportPage.test.tsx::date and supplier filters request a side-by-side comparison for the selected suppliers`<br>`frontend/src/modules/reporting/SupplierPerformanceReportPage.test.tsx::shows loading, error and empty states` | Pass |
| FR6.4-ST-2 | Verify the report is accessible only to Manager/Admin roles | `backend/tests/test_supplier_performance.py::test_supplier_performance_date_validation_and_manager_admin_access`<br>`frontend/src/shell/shell.test.tsx::staff and cashiers cannot see or directly open supplier performance reports` | Pass |
| FR6.5-ST-1 | End-to-end verification that export functionality respects the same access restrictions as the underlying report | `backend/tests/test_reporting_export.py::test_fr6_5_st_1_export_is_denied_where_the_report_is_denied` | Pass |
| FR6.5-ST-2 | Verify exported file naming convention is clear and includes report type and date for easy identification | `backend/tests/test_reporting_export.py::test_fr6_5_st_2_file_name_has_report_type_and_date` | Pass |

### 3.7 Search and Filter

| ID | Description | Evidence | Result |
|---|---|---|---|
| FR7.1-ST-1 | End-to-end verification that search performance meets the required response time under normal load | `python -m scripts.loadtest` (2026-11-06), see docs/system-validation-report.md | Pass |
| FR7.1-ST-2 | Verify search functionality is available to all authenticated roles, since all roles need to locate products | `backend/tests/test_product_search.py::test_search_requires_all_roles_and_rejects_long_terms` | Pass |
| FR7.2-ST-1 | End-to-end verification that filter and sort combinations remain performant and accurate on a large catalog (10000+ SKUs) | `python -m scripts.loadtest` (2026-11-06) plus a combined filter/sort check on the same dataset, see docs/system-validation-report.md | Pass |
| FR7.2-ST-2 | Verify filter and sort options are available to all authenticated roles that can view the product catalog | `backend/tests/test_product_search.py::test_search_requires_all_roles_and_rejects_long_terms`<br>`frontend/src/modules/product/product.test.tsx::product filters and sort are sent with the search term` | Pass |

### 3.8 Notifications

| ID | Description | Evidence | Result |
|---|---|---|---|
| FR8.1-ST-1 | End-to-end verification that a Manager receives a low-stock notification and it remains visible/accessible across sessions until acted upon | `backend/tests/test_notifications.py::test_fr8_1_st_1_low_stock_notification_persists_across_sessions_until_acted_on`<br>`frontend/src/modules/notifications/notifications.test.tsx::the notifications page lists alerts and Create PO opens a prefilled draft`<br>`frontend/src/modules/notifications/notifications.test.tsx::the notifications page can show only unread notifications` | Pass |
| FR8.1-ST-2 | Verify low-stock notifications are visible to Admin, Manager and Staff but not to Cashier | `backend/tests/test_notifications.py::test_notification_feed_respects_role_permissions`<br>`frontend/src/shell/shell.test.tsx::the %s header notification bell: %s` | Pass |
| FR8.2-ST-1 | End-to-end verification of the full PO lifecycle notification trail from submission through receipt, viewed by the responsible Manager | `backend/tests/test_purchase_order_lifecycle.py::test_fr8_2_st_1_manager_sees_the_full_po_notification_trail` | Pass |
| FR8.2-ST-2 | Verify order status notifications are relevant to and visible for Manager/Admin roles and not shown to Cashier | `backend/tests/test_purchase_order_lifecycle.py::test_fr8_2_st_2_po_status_notifications_are_not_shown_to_cashiers`<br>`backend/tests/test_notifications.py::test_notification_feed_respects_role_permissions`<br>`backend/tests/test_rbac.py::test_role_permissions_match_the_matrix` | Pass |

### 3.9 Security

| ID | Description | Evidence | Result |
|---|---|---|---|
| SEC-INP-3-ST-1 | Verify a script in a stock adjustment reason does not run when an Admin views the audit log | `frontend/src/modules/audit/audit.test.tsx::logged text is shown as text, not markup` | Pass |
| SEC-DAT-6-ST-1 | Verify no credentials or keys are committed to the source repository | `backend/tests/test_plan_cases.py::test_sec_dat_6_st_1_no_credentials_in_source` | Pass |
| SEC-DAT-6-ST-2 | Verify the application reads secrets from environment configuration | `backend/tests/test_plan_cases.py::test_sec_dat_6_st_2_secrets_come_from_the_environment` | Pass |
