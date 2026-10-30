# Test plan traceability

Maps every case in `Documents/Test_Plan_Document.docx` to the automated tests that cover it.
`tests/test_traceability.py` checks that this table lists all 226 cases and that each test it names exists.

Status:

- **Automated**: the case is fully covered by the tests named.
- **Partial**: part of the case is covered; the note says what is missing.
- **Manual**: not automated, with the reason in the note.
- **Pending**: the feature the case exercises is not in `main` yet. The issue that adds it should add the test.

Test references are in `backend/tests` unless prefixed `fe:`, which is `frontend/src`. Tests written for this table are named after their ID (`test_fr1_1_it_3_...` in `test_plan_cases.py`).

Totals: 226 cases, 146 automated, 17 partial, 1 manual, 62 pending.


## 3.1 Product Management

24 cases: 22 automated, 2 pending.

| ID | Status | Tests | Note |
|---|---|---|---|
| FR1.1-UT-1 | Automated | `test_products.py::test_manager_creates_and_lists_product` |  |
| FR1.1-UT-2 | Automated | `test_products.py::test_product_validation_rejects_duplicate_blank_and_negative` ; `test_constraints.py::test_duplicate_product_sku_rejected` |  |
| FR1.1-UT-3 | Automated | `test_products.py::test_product_validation_rejects_duplicate_blank_and_negative` |  |
| FR1.1-IT-1 | Automated | `test_products.py::test_price_update_is_visible_to_cashier_and_audited` |  |
| FR1.1-IT-2 | Automated | `test_products.py::test_delete_requires_zero_stock_and_cashier_cannot_manage` |  |
| FR1.1-IT-3 | Automated | `test_plan_cases.py::test_fr1_1_it_3_uploaded_image_is_stored_and_served` |  |
| FR1.1-ST-1 | Automated | `test_plan_cases.py::test_fr1_1_st_1_add_product_flow_from_login_to_catalog` | Driven through the API; the browser steps are covered by the product screen tests |
| FR1.1-ST-2 | Automated | `test_products.py::test_delete_requires_zero_stock_and_cashier_cannot_manage` ; `fe:modules/product/product.test.tsx::cashier cannot open product management but can see search placeholder` |  |
| FR1.2-UT-1 | Automated | `test_categories.py::test_admin_creates_tree_in_tree_order_and_invalid_parent_is_not_saved` |  |
| FR1.2-UT-2 | Automated | `test_categories.py::test_admin_creates_tree_in_tree_order_and_invalid_parent_is_not_saved` |  |
| FR1.2-UT-3 | Automated | `test_categories.py::test_admin_creates_tree_in_tree_order_and_invalid_parent_is_not_saved` |  |
| FR1.2-IT-1 | Automated | `test_categories.py::test_cycles_duplicates_delete_and_rollup_counts` |  |
| FR1.2-IT-2 | Automated | `test_categories.py::test_cycles_duplicates_delete_and_rollup_counts` |  |
| FR1.2-IT-3 | Automated | `test_categories.py::test_cycles_duplicates_delete_and_rollup_counts` ; `test_product_search.py::test_search_matches_name_sku_brand_variant_and_category` | Products reference a category by id, so a rename shows everywhere |
| FR1.2-ST-1 | Automated | `test_categories.py::test_admin_creates_tree_in_tree_order_and_invalid_parent_is_not_saved` ; `fe:modules/product/product.test.tsx::category tree shows hierarchy and staff is denied category management` |  |
| FR1.2-ST-2 | Automated | `test_categories.py::test_staff_and_cashier_can_read_but_cannot_manage` |  |
| FR1.3-UT-1 | Automated | `test_variants.py::test_variants_normalize_attributes_and_use_effective_price` |  |
| FR1.3-UT-2 | Automated | `test_variants.py::test_duplicate_variant_combination_and_sku_are_field_errors` ; `test_constraints.py::test_duplicate_variant_combination_rejected` |  |
| FR1.3-UT-3 | Automated | `test_variants.py::test_variants_normalize_attributes_and_use_effective_price` |  |
| FR1.3-IT-1 | Automated | `test_variants.py::test_variant_stock_is_independent_and_delete_is_soft` |  |
| FR1.3-IT-2 | Pending |  | Sales transactions are not in main yet (#24) |
| FR1.3-IT-3 | Automated | `test_variants.py::test_variant_stock_is_independent_and_delete_is_soft` |  |
| FR1.3-ST-1 | Pending |  | Sales transactions are not in main yet (#24) |
| FR1.3-ST-2 | Automated | `test_variants.py::test_variants_normalize_attributes_and_use_effective_price` ; `test_variants.py::test_duplicate_variant_combination_and_sku_are_field_errors` |  |

## 3.2 Stock Management

40 cases: 26 automated, 3 partial, 1 manual, 10 pending.

| ID | Status | Tests | Note |
|---|---|---|---|
| FR2.1-UT-1 | Automated | `test_stock_levels.py::test_stock_levels_are_per_location_and_expose_combined_totals` |  |
| FR2.1-UT-2 | Automated | `test_stock_levels.py::test_stock_levels_are_per_location_and_expose_combined_totals` |  |
| FR2.1-UT-3 | Automated | `test_constraints.py::test_negative_stock_rejected` ; `test_stock_adjustments.py::test_adjustment_below_zero_is_blocked` |  |
| FR2.1-IT-1 | Automated | `test_stock_transfers.py::test_transfer_updates_stock_movements_audit_and_valuation` ; `test_stock_transfers.py::test_transfer_of_25_updates_both_balances_and_alerts` |  |
| FR2.1-IT-2 | Automated | `test_stock_transfers.py::test_transfer_updates_stock_movements_audit_and_valuation` ; `test_reporting_stock.py::test_valuation_is_live_and_can_filter_location` |  |
| FR2.1-IT-3 | Automated | `test_sales_availability.py::test_cashier_availability_uses_only_assigned_location` |  |
| FR2.1-ST-1 | Automated | `test_stock_locations.py::test_admin_and_manager_can_create_and_edit_locations` ; `test_stock_levels.py::test_stock_levels_are_per_location_and_expose_combined_totals` ; `fe:modules/stock/LocationsPage.test.tsx::lists active and inactive locations and adds a new one` |  |
| FR2.1-ST-2 | Automated | `test_stock_levels.py::test_staff_stock_levels_are_scoped_to_assigned_location` ; `test_rbac.py::test_staff_see_only_their_own_location` |  |
| FR2.2-UT-1 | Pending |  | Sales transactions are not in main yet (#24) |
| FR2.2-UT-2 | Partial | `test_purchase_orders.py::test_receipt_hook_advances_lifecycle_notifies_and_freezes_lines` ; `test_notifications.py::test_shared_stock_updates_create_distinct_alerts_and_clear_on_recovery` | PO receiving is not in main yet (#22); the shared stock update with a receipt movement is tested |
| FR2.2-UT-3 | Automated | `test_stock_transfers.py::test_transfer_updates_stock_movements_audit_and_valuation` |  |
| FR2.2-IT-1 | Partial | `test_stock_transfers.py::test_shared_stock_update_locks_balance_and_rejects_insufficient_stock` | Sales transactions are not in main yet (#24); the shared stock update that a sale will use rejects it |
| FR2.2-IT-2 | Pending |  | PO receiving is not in main yet (#22) |
| FR2.2-IT-3 | Pending |  | Sales transactions are not in main yet (#24); Invoices are not in main yet (#26) |
| FR2.2-ST-1 | Pending |  | Sales transactions are not in main yet (#24); PO receiving is not in main yet (#22) |
| FR2.2-ST-2 | Manual | `test_reporting_stock.py::test_valuation_is_live_and_can_filter_location` | Dashboard refresh timing needs a browser on a running stack; the API reads live data |
| FR2.3-UT-1 | Automated | `test_notifications.py::test_shared_stock_updates_create_distinct_alerts_and_clear_on_recovery` |  |
| FR2.3-UT-2 | Automated | `test_notifications.py::test_shared_stock_updates_create_distinct_alerts_and_clear_on_recovery` |  |
| FR2.3-UT-3 | Automated | `test_plan_cases.py::test_fr2_3_ut_3_and_fr8_1_ut_2_alert_only_at_or_below_threshold` |  |
| FR2.3-IT-1 | Automated | `test_notifications.py::test_shared_stock_updates_create_distinct_alerts_and_clear_on_recovery` | Recovery goes through a receipt movement |
| FR2.3-IT-2 | Automated | `test_notifications.py::test_alerts_are_location_scoped_and_align_with_reorder_report` |  |
| FR2.3-IT-3 | Automated | `test_notifications.py::test_alerts_are_location_scoped_and_align_with_reorder_report` |  |
| FR2.3-ST-1 | Pending |  | Create-PO-from-alert action is not built (#28) |
| FR2.3-ST-2 | Automated | `test_notifications.py::test_threshold_changes_reevaluate_immediately_and_cashier_is_denied` ; `fe:modules/stock/StockLevelsPage.test.tsx::saves reorder settings for a stock record` |  |
| FR2.4-UT-1 | Automated | `test_stock_adjustments.py::test_negative_adjustment_reduces_stock_and_logs_reason` |  |
| FR2.4-UT-2 | Automated | `test_stock_adjustments.py::test_blank_reason_is_rejected_and_stock_unchanged` ; `test_constraints.py::test_adjustment_requires_reason` |  |
| FR2.4-UT-3 | Automated | `test_stock_adjustments.py::test_positive_adjustment_increases_stock` |  |
| FR2.4-IT-1 | Automated | `test_stock_adjustments.py::test_negative_adjustment_reduces_stock_and_logs_reason` ; `test_constraints.py::test_audit_log_is_append_only` |  |
| FR2.4-IT-2 | Automated | `test_plan_cases.py::test_fr2_4_it_2_adjustment_is_in_the_valuation_report` |  |
| FR2.4-IT-3 | Automated | `test_stock_adjustments.py::test_adjustment_below_zero_is_blocked` |  |
| FR2.4-ST-1 | Automated | `test_stock_adjustments.py::test_cashier_is_denied` ; `fe:modules/stock/StockLevelsPage.test.tsx::hides the Adjust action from users without stock.adjust` |  |
| FR2.4-ST-2 | Automated | `test_stock_adjustments.py::test_negative_adjustment_reduces_stock_and_logs_reason` ; `test_plan_cases.py::test_fr2_4_it_2_adjustment_is_in_the_valuation_report` |  |
| FR2.5-UT-1 | Pending |  | PO receiving is not in main yet (#22) |
| FR2.5-UT-2 | Pending |  | PO receiving is not in main yet (#22) |
| FR2.5-UT-3 | Partial | `test_plan_cases.py::test_fr2_5_ut_3_duplicate_serial_number_is_rejected` | Enforced by the database; the entry screen and API arrive with pO receiving is not in main yet (#22) |
| FR2.5-IT-1 | Pending |  | Sales transactions are not in main yet (#24) |
| FR2.5-IT-2 | Automated | `test_returns.py::test_tracked_items_serial_and_batch_returns` |  |
| FR2.5-IT-3 | Pending |  | No batch lookup API yet |
| FR2.5-ST-1 | Pending |  | PO receiving is not in main yet (#22); Sales transactions are not in main yet (#24) |
| FR2.5-ST-2 | Automated | `test_stock_adjustments.py::test_positive_adjustment_increases_stock` ; `test_stock_transfers.py::test_transfer_updates_stock_movements_audit_and_valuation` | Untracked products adjust and transfer with no batch or serial |

## 3.3 Purchasing / Supplier Management

32 cases: 15 automated, 3 partial, 14 pending.

| ID | Status | Tests | Note |
|---|---|---|---|
| FR3.1-UT-1 | Automated | `test_suppliers.py::test_supplier_crud_validates_email_and_records_audit` |  |
| FR3.1-UT-2 | Automated | `test_suppliers.py::test_supplier_crud_validates_email_and_records_audit` ; `fe:modules/purchasing/SuppliersPage.test.tsx::renders supplier management at the guarded route and handles supplier email errors` |  |
| FR3.1-UT-3 | Automated | `test_suppliers.py::test_catalog_crud_validates_prices_references_and_duplicate_associations` |  |
| FR3.1-IT-1 | Automated | `test_purchase_orders.py::test_purchase_order_requires_active_supplier_location_and_catalog_line` ; `fe:modules/purchasing/PurchaseOrdersPage.test.tsx::creates a draft from supplier catalog prices, recalculates totals and submits it` |  |
| FR3.1-IT-2 | Automated | `test_suppliers.py::test_supplier_deactivation_is_blocked_by_open_purchase_orders` |  |
| FR3.1-IT-3 | Automated | `test_plan_cases.py::test_fr3_1_it_3_supplier_edit_shows_on_existing_purchase_order` ; `test_suppliers.py::test_supplier_deactivation_preserves_purchase_order_prices_and_history` |  |
| FR3.1-ST-1 | Automated | `test_purchase_orders.py::test_create_list_view_edit_and_submit_po_calculates_totals_and_audits` ; `fe:modules/purchasing/SuppliersPage.test.tsx::loads supplier catalog and submits product association changes` |  |
| FR3.1-ST-2 | Automated | `test_suppliers.py::test_staff_and_cashier_are_denied_supplier_management` |  |
| FR3.2-UT-1 | Automated | `test_purchase_orders.py::test_create_list_view_edit_and_submit_po_calculates_totals_and_audits` |  |
| FR3.2-UT-2 | Automated | `test_purchase_orders.py::test_purchase_order_rejects_zero_and_negative_quantities` |  |
| FR3.2-UT-3 | Automated | `test_purchase_orders.py::test_create_list_view_edit_and_submit_po_calculates_totals_and_audits` |  |
| FR3.2-IT-1 | Automated | `test_purchase_orders.py::test_receipt_hook_advances_lifecycle_notifies_and_freezes_lines` | Receipts are applied through the purchasing hook |
| FR3.2-IT-2 | Automated | `test_purchase_orders.py::test_receipt_hook_advances_lifecycle_notifies_and_freezes_lines` |  |
| FR3.2-IT-3 | Automated | `test_purchase_orders.py::test_cancelled_orders_are_excluded_from_pending_orders` |  |
| FR3.2-ST-1 | Partial | `test_purchase_orders.py::test_create_list_view_edit_and_submit_po_calculates_totals_and_audits` ; `test_purchase_orders.py::test_receipt_hook_advances_lifecycle_notifies_and_freezes_lines` | PO receiving is not in main yet (#22) |
| FR3.2-ST-2 | Automated | `test_purchase_orders.py::test_admin_can_manage_purchase_orders_staff_and_cashier_are_denied` |  |
| FR3.3-UT-1 | Pending |  | PO receiving is not in main yet (#22) |
| FR3.3-UT-2 | Pending |  | PO receiving is not in main yet (#22) |
| FR3.3-UT-3 | Partial | `test_constraints.py::test_po_line_cannot_receive_more_than_ordered` | Enforced by the database; PO receiving is not in main yet (#22) |
| FR3.3-IT-1 | Pending |  | PO receiving is not in main yet (#22) |
| FR3.3-IT-2 | Pending |  | PO receiving is not in main yet (#22); Supplier pricing history is not in main yet (#23) |
| FR3.3-IT-3 | Pending |  | PO receiving is not in main yet (#22) |
| FR3.3-ST-1 | Pending |  | PO receiving is not in main yet (#22) |
| FR3.3-ST-2 | Pending |  | PO receiving is not in main yet (#22) |
| FR3.4-UT-1 | Pending |  | Supplier pricing history is not in main yet (#23) |
| FR3.4-UT-2 | Pending |  | Supplier pricing history is not in main yet (#23) |
| FR3.4-UT-3 | Pending |  | Supplier pricing history is not in main yet (#23) |
| FR3.4-IT-1 | Pending |  | Supplier pricing history is not in main yet (#23); supplier performance report is #33 |
| FR3.4-IT-2 | Partial | `test_constraints.py::test_supplier_price_history_is_append_only` | Append-only in the database; supplier pricing history is not in main yet (#23) |
| FR3.4-IT-3 | Pending |  | Supplier pricing history is not in main yet (#23) |
| FR3.4-ST-1 | Pending |  | Supplier pricing history is not in main yet (#23) |
| FR3.4-ST-2 | Pending |  | Supplier pricing history is not in main yet (#23) |

## 3.4 Sales / Orders

24 cases: 9 automated, 5 partial, 10 pending.

| ID | Status | Tests | Note |
|---|---|---|---|
| FR4.1-UT-1 | Pending |  | Sales transactions are not in main yet (#24) |
| FR4.1-UT-2 | Pending |  | Sales transactions are not in main yet (#24) |
| FR4.1-UT-3 | Pending |  | Sales transactions are not in main yet (#24) |
| FR4.1-IT-1 | Pending |  | Sales transactions are not in main yet (#24) |
| FR4.1-IT-2 | Pending |  | Sales transactions are not in main yet (#24) |
| FR4.1-IT-3 | Pending |  | Sales transactions are not in main yet (#24); sales trend report is #31 |
| FR4.1-ST-1 | Pending |  | Sales transactions are not in main yet (#24); Invoices are not in main yet (#26) |
| FR4.1-ST-2 | Pending |  | Sales transactions are not in main yet (#24) |
| FR4.2-UT-1 | Automated | `test_returns.py::test_fr4_2_ut_1_valid_return_generates_credit_note` |  |
| FR4.2-UT-2 | Automated | `test_returns.py::test_fr4_2_ut_2_resaleable_unit_restocks_inventory` |  |
| FR4.2-UT-3 | Automated | `test_returns.py::test_fr4_2_ut_3_invoice_lookup_valid_and_invalid` |  |
| FR4.2-IT-1 | Automated | `test_returns.py::test_fr4_2_it_1_damaged_line_not_restocked_and_mixed_return` ; `test_constraints.py::test_damaged_return_cannot_be_restocked` |  |
| FR4.2-IT-2 | Automated | `test_returns.py::test_fr4_2_it_2_late_return_manager_override_and_lockout` |  |
| FR4.2-IT-3 | Pending | `test_returns.py::test_fr4_2_it_3_net_sales_data_aggregatable` | Sales trend report is #31; test confirms return data supports netting |
| FR4.2-ST-1 | Partial | `test_returns.py::test_fr4_2_st_1_end_to_end_sale_to_return` | End-to-end return automated through API; sales trend netting is pending #31 |
| FR4.2-ST-2 | Automated | `test_returns.py::test_authorization_and_location_scoping` |  |
| FR4.3-UT-1 | Automated | `test_invoices.py::test_fr4_3_ut_1_invoice_snapshot_is_available_with_the_sale` |  |
| FR4.3-UT-2 | Automated | `test_invoices.py::test_fr4_3_ut_2_sale_persists_required_invoice_snapshot` |  |
| FR4.3-UT-3 | Partial | `test_invoices.py::test_fr4_3_ut_2_sale_persists_required_invoice_snapshot` | Covers 30000 + 18% GST; multi-line paise rounding and invariant rollback remain uncovered |
| FR4.3-IT-1 | Partial | `test_invoices.py::test_fr4_3_it_1_invoice_row_rejects_updates` | Database rejects invoice updates; catalog rename and repeat-render snapshot checks remain uncovered |
| FR4.3-IT-2 | Pending |  | Return status and byte-identical sale, line and invoice records before/after return remain uncovered |
| FR4.3-IT-3 | Partial | `test_invoices.py::test_fr4_3_it_3_history_finds_a_seven_year_old_sale_by_date_and_number` ; `test_invoices.py::test_retention_rejects_deleting_a_recent_invoice` ; `test_retention.py::test_retention_archive_dry_run_then_execute_is_verified_and_repeatable` | Seven-year history, retention delete, and archive are covered; 7 years 364 days and old PDF retrieval remain untested |
| FR4.3-ST-1 | Automated | `test_invoices.py::test_fr4_3_st_1_twenty_parallel_cashiers_get_distinct_invoice_numbers` ; `test_constraints.py::test_invoice_numbers_unique_and_sequential` |  |
| FR4.3-ST-2 | Partial | `test_invoices.py::test_fr4_3_st_2_invoice_pdf_has_attachment_headers_and_snapshot_text` | Covers invoice PDF headers and key totals; long multi-page invoices and credit note PDF extraction remain uncovered |

## 3.5 User Management

24 cases: 23 automated, 1 partial.

| ID | Status | Tests | Note |
|---|---|---|---|
| FR5.1-UT-1 | Automated | `test_users.py::test_admin_creates_manager_and_invite_is_not_exposed` |  |
| FR5.1-UT-2 | Automated | `test_rbac.py::test_role_permissions_match_the_matrix` ; `test_rbac.py::test_api_enforces_the_matrix_for_every_role` |  |
| FR5.1-UT-3 | Automated | `test_rbac.py::test_role_permissions_match_the_matrix` ; `test_rbac.py::test_api_enforces_the_matrix_for_every_role` |  |
| FR5.1-IT-1 | Automated | `test_rbac.py::test_role_change_applies_to_the_next_request` ; `test_users.py::test_role_change_applies_on_the_next_request` |  |
| FR5.1-IT-2 | Automated | `test_rbac.py::test_api_enforces_the_matrix_for_every_role` |  |
| FR5.1-IT-3 | Automated | `test_rbac.py::test_me_lists_the_role_permissions` ; `fe:shell/shell.test.tsx::EXPECTED_MENU` |  |
| FR5.1-ST-1 | Automated | `test_rbac.py::test_api_enforces_the_matrix_for_every_role` ; `test_rbac.py::test_staff_see_only_their_own_location` |  |
| FR5.1-ST-2 | Automated | `test_users.py::test_non_admin_cannot_call_management_endpoints` ; `fe:modules/auth/UsersPage.test.tsx::Manager opening users sees Access denied` |  |
| FR5.2-UT-1 | Automated | `test_auth.py::test_valid_credentials_log_in` ; `fe:modules/auth/auth.test.tsx::valid credentials open the role dashboard` |  |
| FR5.2-UT-2 | Automated | `test_auth.py::test_invalid_credentials_get_generic_error` ; `fe:modules/auth/auth.test.tsx::invalid credentials show the generic error` |  |
| FR5.2-UT-3 | Automated | `test_auth.py::test_every_non_public_route_requires_a_session` ; `test_auth.py::test_protected_endpoint_without_session_gets_401` ; `fe:modules/auth/auth.test.tsx::an internal URL without a session shows the login page` |  |
| FR5.2-IT-1 | Automated | `test_auth.py::test_idle_session_expires` ; `fe:modules/auth/auth.test.tsx::a request rejected for an expired session sends the user to log in` |  |
| FR5.2-IT-2 | Automated | `test_rbac.py::test_per_action_check_within_a_screen` |  |
| FR5.2-IT-3 | Automated | `test_auth.py::test_passwords_are_stored_as_salted_hashes` ; `test_auth.py::test_password_reset_flow` |  |
| FR5.2-ST-1 | Automated | `test_auth.py::test_logout_invalidates_session_on_server` ; `test_rbac.py::test_api_enforces_the_matrix_for_every_role` ; `fe:modules/auth/auth.test.tsx::sign out returns to the login page` |  |
| FR5.2-ST-2 | Automated | `test_auth.py::test_lockout_after_five_failures_blocks_correct_password` |  |
| FR5.3-UT-1 | Automated | `test_audit.py::test_login_is_logged_with_user_and_time` |  |
| FR5.3-UT-2 | Automated | `test_audit.py::test_price_edit_is_logged_with_old_and_new_value` ; `fe:modules/audit/audit.test.tsx::entries show who, what and when, with old and new values` |  |
| FR5.3-UT-3 | Automated | `test_audit.py::test_filter_by_user_any_case` ; `fe:modules/audit/audit.test.tsx::filtering by user shows only that user’s entries` |  |
| FR5.3-IT-1 | Automated | `test_audit.py::test_entries_from_every_module_share_one_structure` |  |
| FR5.3-IT-2 | Automated | `test_audit.py::test_api_has_no_way_to_change_entries` ; `test_audit.py::test_admin_cannot_edit_or_delete_an_entry` ; `test_audit.py::test_database_rejects_changes_made_through_the_orm` |  |
| FR5.3-IT-3 | Automated | `test_rbac.py::test_denied_attempt_is_audited` |  |
| FR5.3-ST-1 | Partial | `test_audit.py::test_entries_from_every_module_share_one_structure` | Sales entries arrive with sales transactions are not in main yet (#24) |
| FR5.3-ST-2 | Automated | `test_audit.py::test_only_admin_can_view_the_log` ; `fe:modules/audit/audit.test.tsx::a non-Admin is denied and the log is never requested` |  |

## 3.6 Reporting and Analytics

40 cases: 20 automated, 2 partial, 18 pending.

| ID | Status | Tests | Note |
|---|---|---|---|
| FR6.1-UT-1 | Automated | `test_reporting_stock.py::test_valuation_is_live_and_can_filter_location` ; `test_reporting_stock.py::test_valuation_uses_average_cost_then_active_supplier_catalog_price` |  |
| FR6.1-UT-2 | Automated | `test_reporting_stock.py::test_valuation_is_live_and_can_filter_location` ; `test_reporting_stock.py::test_valuation_uses_average_cost_then_active_supplier_catalog_price` |  |
| FR6.1-UT-3 | Automated | `test_plan_cases.py::test_fr6_1_ut_3_zero_stock_adds_no_value` |  |
| FR6.1-IT-1 | Automated | `test_plan_cases.py::test_fr2_4_it_2_adjustment_is_in_the_valuation_report` |  |
| FR6.1-IT-2 | Pending |  | CSV and PDF export is #34 |
| FR6.1-IT-3 | Automated | `test_reporting_stock.py::test_valuation_is_live_and_can_filter_location` |  |
| FR6.1-ST-1 | Automated | `test_reporting_stock.py::test_valuation_is_live_and_can_filter_location` ; `test_reporting_stock.py::test_staff_cannot_access_stock_reports` ; `test_reporting_stock.py::test_cashier_cannot_access_stock_reports` |  |
| FR6.1-ST-2 | Automated | `test_reporting_stock.py::test_staff_cannot_access_stock_reports` ; `test_reporting_stock.py::test_cashier_cannot_access_stock_reports` ; `test_rbac.py::test_api_enforces_the_matrix_for_every_role` |  |
| FR6.2-UT-1 | Pending |  | Sales trend report is #31 |
| FR6.2-UT-2 | Pending |  | Sales trend report is #31 |
| FR6.2-UT-3 | Pending |  | Sales trend report is #31 |
| FR6.2-IT-1 | Pending |  | Sales trend report is #31 |
| FR6.2-IT-2 | Pending |  | Sales trend report is #31 |
| FR6.2-IT-3 | Pending |  | Sales trend report is #31 |
| FR6.2-ST-1 | Pending |  | Sales trend report is #31 |
| FR6.2-ST-2 | Pending |  | Sales trend report is #31 |
| FR6.3-UT-1 | Automated | `test_reporting_stock.py::test_reorder_report_filters_thresholds_and_uses_reorder_to` |  |
| FR6.3-UT-2 | Automated | `test_reporting_stock.py::test_reorder_report_filters_thresholds_and_uses_reorder_to` |  |
| FR6.3-UT-3 | Automated | `test_reporting_stock.py::test_reorder_report_filters_thresholds_and_uses_reorder_to` |  |
| FR6.3-IT-1 | Automated | `test_purchase_order_receiving.py::test_multiple_receipts_accumulate_and_short_items_remain_outstanding` | PO receipts are reflected through live stock |
| FR6.3-IT-2 | Automated | `test_notifications.py::test_alerts_are_location_scoped_and_align_with_reorder_report` |  |
| FR6.3-IT-3 | Automated | `test_reporting_stock.py::test_reorder_report_filters_thresholds_and_uses_reorder_to` |  |
| FR6.3-ST-1 | Automated | `fe:modules/reporting/LowStockReportPage.test.tsx::low-stock report filters locations and links a prefilled PO` ; `fe:modules/purchasing/PurchaseOrdersPage.test.tsx::reorder report links prefill a draft purchase order` |  |
| FR6.3-ST-2 | Automated | `test_reporting_stock.py::test_admin_can_access_reorder_report` ; `test_reporting_stock.py::test_staff_cannot_access_stock_reports` ; `test_reporting_stock.py::test_cashier_cannot_access_stock_reports` ; `test_rbac.py::test_api_enforces_the_matrix_for_every_role` |  |
| FR6.4-UT-1 | Pending |  | Supplier performance report is #33 |
| FR6.4-UT-2 | Pending |  | Supplier performance report is #33 |
| FR6.4-UT-3 | Pending |  | Supplier performance report is #33 |
| FR6.4-IT-1 | Pending |  | Supplier performance report is #33 |
| FR6.4-IT-2 | Pending |  | Supplier performance report is #33 |
| FR6.4-IT-3 | Pending |  | Supplier performance report is #33 |
| FR6.4-ST-1 | Pending |  | Supplier performance report is #33 |
| FR6.4-ST-2 | Pending |  | Supplier performance report is #33 |
| FR6.5-UT-1 | Automated | `test_reporting_export.py::test_fr6_5_every_report_exports_in_both_formats` ; `test_reporting_export.py::test_fr6_5_csv_matches_the_on_screen_valuation` |  |
| FR6.5-UT-2 | Automated | `test_reporting_export.py::test_fr6_5_every_report_exports_in_both_formats` |  |
| FR6.5-UT-3 | Automated | `test_reporting_export.py::test_fr6_5_ut_3_commas_and_quotes_stay_in_one_cell` |  |
| FR6.5-IT-1 | Partial | `test_reporting_export.py::test_fr6_5_every_report_exports_in_both_formats` | Covers the valuation and reorder reports; sales trend (#31) and supplier performance (#33) are not in `main` yet |
| FR6.5-IT-2 | Automated | `test_reporting_export.py::test_fr6_5_it_2_pdf_header_has_title_time_and_filter` |  |
| FR6.5-IT-3 | Automated | `test_reporting_export.py::test_fr6_5_it_3_five_thousand_rows_export_without_truncation` |  |
| FR6.5-ST-1 | Automated | `test_reporting_export.py::test_fr6_5_st_1_export_is_denied_where_the_report_is_denied` |  |
| FR6.5-ST-2 | Automated | `test_reporting_export.py::test_fr6_5_st_2_file_name_has_report_type_and_date` |  |

## 3.7 Search and Filter

16 cases: 14 automated, 2 pending.

| ID | Status | Tests | Note |
|---|---|---|---|
| FR7.1-UT-1 | Automated | `test_product_search.py::test_search_matches_name_sku_brand_variant_and_category` |  |
| FR7.1-UT-2 | Automated | `test_product_search.py::test_search_matches_name_sku_brand_variant_and_category` |  |
| FR7.1-UT-3 | Automated | `test_product_search.py::test_search_matches_name_sku_brand_variant_and_category` |  |
| FR7.1-IT-1 | Automated | `test_product_search.py::test_search_is_literal_live_and_location_scoped` |  |
| FR7.1-IT-2 | Automated | `test_product_search.py::test_search_matches_name_sku_brand_variant_and_category` |  |
| FR7.1-IT-3 | Automated | `test_product_search.py::test_search_matches_name_sku_brand_variant_and_category` | API returns an empty page; the empty-state text is in the screen tests |
| FR7.1-ST-1 | Pending |  | Response-time check belongs to performance testing (#35) |
| FR7.1-ST-2 | Automated | `test_product_search.py::test_search_requires_all_roles_and_rejects_long_terms` |  |
| FR7.2-UT-1 | Automated | `test_product_filters.py::test_category_and_price_range_return_exactly_the_intersection` |  |
| FR7.2-UT-2 | Automated | `test_product_filters.py::test_category_and_price_range_return_exactly_the_intersection` |  |
| FR7.2-UT-3 | Automated | `test_product_filters.py::test_price_and_stock_sorts_work_both_ways_on_live_data` |  |
| FR7.2-IT-1 | Automated | `test_product_filters.py::test_category_and_price_range_return_exactly_the_intersection` |  |
| FR7.2-IT-2 | Automated | `test_product_filters.py::test_price_and_stock_sorts_work_both_ways_on_live_data` |  |
| FR7.2-IT-3 | Automated | `test_product_filters.py::test_stock_status_filter_is_scoped_to_the_users_location` |  |
| FR7.2-ST-1 | Pending |  | 10,000-SKU catalog timing belongs to performance testing (#35) |
| FR7.2-ST-2 | Automated | `test_product_search.py::test_search_requires_all_roles_and_rejects_long_terms` ; `fe:modules/product/product.test.tsx::product filters and sort are sent with the search term` |  |

## 3.8 Notifications

16 cases: 11 automated, 1 partial, 4 pending.

| ID | Status | Tests | Note |
|---|---|---|---|
| FR8.1-UT-1 | Automated | `test_notifications.py::test_shared_stock_updates_create_distinct_alerts_and_clear_on_recovery` |  |
| FR8.1-UT-2 | Automated | `test_plan_cases.py::test_fr2_3_ut_3_and_fr8_1_ut_2_alert_only_at_or_below_threshold` |  |
| FR8.1-UT-3 | Pending |  | Marking a notification read is #28 |
| FR8.1-IT-1 | Automated | `test_notifications.py::test_alerts_are_location_scoped_and_align_with_reorder_report` |  |
| FR8.1-IT-2 | Automated | `test_notifications.py::test_alerts_are_location_scoped_and_align_with_reorder_report` |  |
| FR8.1-IT-3 | Automated | `test_notifications.py::test_shared_stock_updates_create_distinct_alerts_and_clear_on_recovery` |  |
| FR8.1-ST-1 | Pending |  | Notification screen is #28 |
| FR8.1-ST-2 | Automated | `test_rbac.py::test_role_permissions_match_the_matrix` ; `test_notifications.py::test_threshold_changes_reevaluate_immediately_and_cashier_is_denied` |  |
| FR8.2-UT-1 | Automated | `test_purchase_orders.py::test_create_list_view_edit_and_submit_po_calculates_totals_and_audits` |  |
| FR8.2-UT-2 | Automated | `test_purchase_orders.py::test_receipt_hook_advances_lifecycle_notifies_and_freezes_lines` |  |
| FR8.2-UT-3 | Automated | `test_purchase_orders.py::test_create_list_view_edit_and_submit_po_calculates_totals_and_audits` |  |
| FR8.2-IT-1 | Automated | `test_purchase_orders.py::test_admin_creator_is_notified_of_po_status_changes` |  |
| FR8.2-IT-2 | Automated | `test_purchase_orders.py::test_cancelled_orders_are_excluded_from_pending_orders` |  |
| FR8.2-IT-3 | Pending |  | Order status notification list is #29 |
| FR8.2-ST-1 | Pending |  | Order status notification screen is #29 |
| FR8.2-ST-2 | Partial | `test_rbac.py::test_role_permissions_match_the_matrix` | Order status notification screen is #29 |

## 3.9 Security

10 cases: 6 automated, 2 partial, 2 pending.

| ID | Status | Tests | Note |
|---|---|---|---|
| SEC-AUTH-2-UT-1 | Automated | `test_auth.py::test_passwords_are_stored_as_salted_hashes` | Checks the Argon2id prefix |
| SEC-AUTH-2-UT-2 | Automated | `test_auth.py::test_passwords_are_stored_as_salted_hashes` |  |
| SEC-INP-2-IT-1 | Automated | `test_plan_cases.py::test_sec_inp_2_it_1_search_is_not_injectable` ; `test_product_search.py::test_search_is_literal_live_and_location_scoped` |  |
| SEC-INP-2-IT-2 | Automated | `test_plan_cases.py::test_sec_inp_2_it_2_filter_and_sort_parameters_are_not_injectable` |  |
| SEC-INP-3-IT-1 | Partial | `test_plan_cases.py::test_sec_inp_3_it_1_script_in_product_name_is_returned_as_data` | The API returns the name as JSON text; the screen tests do not yet render a script name |
| SEC-INP-3-ST-1 | Automated | `fe:modules/audit/audit.test.tsx::logged text is shown as text, not markup` |  |
| SEC-SES-4-IT-1 | Automated | `test_csrf.py::test_sec_ses_4_it_1_request_without_token_is_rejected` |  |
| SEC-SES-4-IT-2 | Automated | `test_csrf.py::test_sec_ses_4_it_2_request_with_token_succeeds` ; `fe:api.test.ts` |  |
| SEC-DAT-6-ST-1 | Partial | `test_plan_cases.py::test_sec_dat_6_st_1_no_credentials_in_source` | Scans the backend sources; CI also runs gitleaks over the full history (`secret-scan` job) |
| SEC-DAT-6-ST-2 | Automated | `test_plan_cases.py::test_sec_dat_6_st_2_secrets_come_from_the_environment` |  |
