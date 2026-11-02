# Test plan traceability

Maps every case in `Documents/Test_Plan_Document.docx` to the automated tests that cover it.
`tests/test_traceability.py` checks that this table lists all 226 cases and that each test it names exists.

Status:

- **Automated**: the case is fully covered by the tests named.
- **Partial**: part of the case is covered; the note says what is missing.
- **Manual**: not automated, with the reason in the note.
- **Pending**: the feature the case exercises is not in `main` yet. The issue that adds it should add the test.

Test references are in `backend/tests` unless prefixed `fe:`, which is `frontend/src`. Tests written for this table are named after their ID (`test_fr1_1_it_3_...` in `test_plan_cases.py`).

Totals: 226 cases, 223 automated, 3 manual.


## 3.1 Product Management

24 cases: 24 automated.

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
| FR1.3-IT-2 | Automated | `test_sales.py::test_fr1_3_it_2_selling_a_variant_deducts_only_that_variant` |  |
| FR1.3-IT-3 | Automated | `test_variants.py::test_variant_stock_is_independent_and_delete_is_soft` |  |
| FR1.3-ST-1 | Automated | `test_sales.py::test_fr1_3_st_1_cashier_sells_a_chosen_variant_at_its_price_and_invoice_shows_it` | Driven through the API: search, variant list, availability, sale, invoice |
| FR1.3-ST-2 | Automated | `test_variants.py::test_variants_normalize_attributes_and_use_effective_price` ; `test_variants.py::test_duplicate_variant_combination_and_sku_are_field_errors` |  |

## 3.2 Stock Management

40 cases: 39 automated, 1 manual.

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
| FR2.2-UT-1 | Automated | `test_sales.py::test_fr4_1_ut_2_and_fr2_2_ut_1_stock_drops_by_exactly_the_sold_quantity` |  |
| FR2.2-UT-2 | Automated | `test_purchase_order_receiving.py::test_full_receipt_updates_stock_cost_history_audit_and_status_notifications` |  |
| FR2.2-UT-3 | Automated | `test_stock_transfers.py::test_transfer_updates_stock_movements_audit_and_valuation` |  |
| FR2.2-IT-1 | Automated | `test_sales.py::test_fr2_2_it_1_sale_above_available_stock_is_rejected_and_stock_unchanged` |  |
| FR2.2-IT-2 | Automated | `test_purchase_order_receiving.py::test_multiple_receipts_accumulate_and_short_items_remain_outstanding` ; `test_purchase_order_lifecycle.py::test_fr3_3_st_1_staff_finish_a_po_over_two_sessions` |  |
| FR2.2-IT-3 | Automated | `test_sales.py::test_fr2_2_it_3_failure_after_stock_deduction_leaves_no_sale_invoice_or_stock_change` | The interruption is simulated after the stock is deducted and the invoice built |
| FR2.2-ST-1 | Automated | `test_sales.py::test_fr2_2_st_1_sale_receipt_and_transfer_cycle_keeps_both_locations_exact` |  |
| FR2.2-ST-2 | Manual | `test_reporting_stock.py::test_valuation_is_live_and_can_filter_location` | Dashboard refresh timing needs a browser on a running stack; the API reads live data |
| FR2.3-UT-1 | Automated | `test_notifications.py::test_shared_stock_updates_create_distinct_alerts_and_clear_on_recovery` |  |
| FR2.3-UT-2 | Automated | `test_notifications.py::test_shared_stock_updates_create_distinct_alerts_and_clear_on_recovery` |  |
| FR2.3-UT-3 | Automated | `test_plan_cases.py::test_fr2_3_ut_3_and_fr8_1_ut_2_alert_only_at_or_below_threshold` |  |
| FR2.3-IT-1 | Automated | `test_notifications.py::test_shared_stock_updates_create_distinct_alerts_and_clear_on_recovery` | Recovery goes through a receipt movement |
| FR2.3-IT-2 | Automated | `test_notifications.py::test_alerts_are_location_scoped_and_align_with_reorder_report` |  |
| FR2.3-IT-3 | Automated | `test_notifications.py::test_alerts_are_location_scoped_and_align_with_reorder_report` |  |
| FR2.3-ST-1 | Automated | `test_notifications.py::test_shared_stock_updates_create_distinct_alerts_and_clear_on_recovery` ; `fe:modules/notifications/notifications.test.tsx::the notifications page lists alerts and Create PO opens a prefilled draft` ; `fe:modules/notifications/notifications.test.tsx::a link in the bell panel marks the notification read and then navigates` |  |
| FR2.3-ST-2 | Automated | `test_notifications.py::test_threshold_changes_reevaluate_immediately_and_cashier_is_denied` ; `fe:modules/stock/StockLevelsPage.test.tsx::saves reorder settings for a stock record` |  |
| FR2.4-UT-1 | Automated | `test_stock_adjustments.py::test_negative_adjustment_reduces_stock_and_logs_reason` |  |
| FR2.4-UT-2 | Automated | `test_stock_adjustments.py::test_blank_reason_is_rejected_and_stock_unchanged` ; `test_constraints.py::test_adjustment_requires_reason` |  |
| FR2.4-UT-3 | Automated | `test_stock_adjustments.py::test_positive_adjustment_increases_stock` |  |
| FR2.4-IT-1 | Automated | `test_stock_adjustments.py::test_negative_adjustment_reduces_stock_and_logs_reason` ; `test_constraints.py::test_audit_log_is_append_only` |  |
| FR2.4-IT-2 | Automated | `test_plan_cases.py::test_fr2_4_it_2_adjustment_is_in_the_valuation_report` |  |
| FR2.4-IT-3 | Automated | `test_stock_adjustments.py::test_adjustment_below_zero_is_blocked` |  |
| FR2.4-ST-1 | Automated | `test_stock_adjustments.py::test_cashier_is_denied` ; `fe:modules/stock/StockLevelsPage.test.tsx::hides the Adjust action from users without stock.adjust` |  |
| FR2.4-ST-2 | Automated | `test_stock_adjustments.py::test_negative_adjustment_reduces_stock_and_logs_reason` ; `test_plan_cases.py::test_fr2_4_it_2_adjustment_is_in_the_valuation_report` |  |
| FR2.5-UT-1 | Automated | `test_purchase_order_receiving.py::test_receipt_integrates_batch_and_serial_tracking` ; `test_batch_serial_tracking.py::test_batch_receipt_sale_and_recall_reports_sold_invoice_and_available_units` |  |
| FR2.5-UT-2 | Automated | `test_purchase_order_receiving.py::test_receipt_integrates_batch_and_serial_tracking` ; `test_batch_serial_tracking.py::test_serial_receipt_sale_and_return_preserve_invoice_trace` |  |
| FR2.5-UT-3 | Automated | `test_purchase_order_receiving.py::test_duplicate_serial_rolls_back_receipt_and_stock` ; `test_plan_cases.py::test_fr2_5_ut_3_duplicate_serial_number_is_rejected` |  |
| FR2.5-IT-1 | Automated | `test_sales.py::test_fr2_5_it_1_selling_a_serial_marks_only_that_unit_sold` |  |
| FR2.5-IT-2 | Automated | `test_returns.py::test_tracked_items_serial_and_batch_returns` |  |
| FR2.5-IT-3 | Automated | `test_sales.py::test_fr2_5_it_3_batch_lookup_by_number_splits_sold_and_in_stock_units` ; `test_sales.py::test_batch_lookup_by_number_is_scoped_to_staff_location_and_denied_to_cashier` ; `fe:modules/stock/BatchRecallPage.test.tsx::looking up a batch number shows stock by location and the invoices it was sold on` |  |
| FR2.5-ST-1 | Automated | `test_sales.py::test_fr2_5_st_1_batch_received_on_a_po_is_traceable_through_sales_to_a_recall` | A product is tracked by batch or by serial, not both, so the 5 units are sold one per invoice |
| FR2.5-ST-2 | Automated | `test_stock_adjustments.py::test_positive_adjustment_increases_stock` ; `test_stock_transfers.py::test_transfer_updates_stock_movements_audit_and_valuation` | Untracked products adjust and transfer with no batch or serial |

## 3.3 Purchasing / Supplier Management

32 cases: 32 automated.

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
| FR3.2-ST-1 | Automated | `test_purchase_order_lifecycle.py::test_fr3_2_st_1_three_line_po_goes_from_creation_to_received_with_stock` |  |
| FR3.2-ST-2 | Automated | `test_purchase_orders.py::test_admin_can_manage_purchase_orders_staff_and_cashier_are_denied` |  |
| FR3.3-UT-1 | Automated | `test_purchase_order_receiving.py::test_full_receipt_updates_stock_cost_history_audit_and_status_notifications` |  |
| FR3.3-UT-2 | Automated | `test_purchase_order_receiving.py::test_multiple_receipts_accumulate_and_short_items_remain_outstanding` |  |
| FR3.3-UT-3 | Automated | `test_purchase_order_receiving.py::test_over_receipt_rejects_without_creating_any_receipt_or_stock_changes` ; `test_purchase_order_receiving.py::test_concurrent_receipts_cannot_exceed_the_outstanding_order_quantity` ; `test_constraints.py::test_po_line_cannot_receive_more_than_ordered` |  |
| FR3.3-IT-1 | Automated | `test_purchase_order_lifecycle.py::test_fr3_3_it_1_receipt_adds_stock_only_at_the_po_receiving_location` |  |
| FR3.3-IT-2 | Automated | `test_supplier_price_history.py::test_receipts_append_price_history_and_filters_keep_supplier_attribution` ; `test_purchase_order_receiving.py::test_full_receipt_updates_stock_cost_history_audit_and_status_notifications` |  |
| FR3.3-IT-3 | Automated | `test_purchase_order_receiving.py::test_multiple_receipts_accumulate_and_short_items_remain_outstanding` ; `test_purchase_order_receiving.py::test_receipt_integrates_batch_and_serial_tracking` |  |
| FR3.3-ST-1 | Automated | `test_purchase_order_lifecycle.py::test_fr3_3_st_1_staff_finish_a_po_over_two_sessions` |  |
| FR3.3-ST-2 | Automated | `test_purchase_order_receiving.py::test_staff_can_receive_only_assigned_location_orders_and_cashier_is_denied` |  |
| FR3.4-UT-1 | Automated | `test_supplier_price_history.py::test_receipts_append_price_history_and_filters_keep_supplier_attribution` |  |
| FR3.4-UT-2 | Automated | `test_supplier_price_history.py::test_receipts_append_price_history_and_filters_keep_supplier_attribution` |  |
| FR3.4-UT-3 | Automated | `test_supplier_price_history.py::test_receipts_append_price_history_and_filters_keep_supplier_attribution` |  |
| FR3.4-IT-1 | Automated | `test_supplier_performance.py::test_supplier_performance_price_trends_match_supplier_and_product_history` |  |
| FR3.4-IT-2 | Automated | `test_supplier_price_history.py::test_supplier_price_history_is_read_only_and_manager_admin_only` ; `test_constraints.py::test_supplier_price_history_is_append_only` |  |
| FR3.4-IT-3 | Automated | `test_supplier_price_history.py::test_receipts_append_price_history_and_filters_keep_supplier_attribution` |  |
| FR3.4-ST-1 | Automated | `test_purchase_order_lifecycle.py::test_fr3_4_st_1_manager_compares_supplier_prices_then_orders_from_the_cheaper` |  |
| FR3.4-ST-2 | Automated | `test_supplier_price_history.py::test_supplier_price_history_is_read_only_and_manager_admin_only` |  |

## 3.4 Sales / Orders

24 cases: 24 automated.

| ID | Status | Tests | Note |
|---|---|---|---|
| FR4.1-UT-1 | Automated | `test_sales.py::test_fr4_1_ut_1_cashier_records_a_sale_for_an_in_stock_product` |  |
| FR4.1-UT-2 | Automated | `test_sales.py::test_fr4_1_ut_2_and_fr2_2_ut_1_stock_drops_by_exactly_the_sold_quantity` |  |
| FR4.1-UT-3 | Automated | `test_sales.py::test_fr4_1_ut_3_zero_stock_is_out_of_stock_and_nothing_is_recorded` |  |
| FR4.1-IT-1 | Automated | `test_sales.py::test_fr4_1_it_1_multi_item_sale_deducts_each_item_and_totals_both` |  |
| FR4.1-IT-2 | Automated | `test_sales.py::test_fr4_1_it_2_two_concurrent_sales_of_the_last_unit_sell_it_once` ; `test_batch_serial_tracking.py::test_concurrent_tracked_sales_cannot_sell_last_unit_twice` |  |
| FR4.1-IT-3 | Automated | `test_sales_trend.py::test_fr6_2_ut_1_and_it_1_sales_trend_ranks_and_nets_returns` | The report includes a sale from the current UTC date range |
| FR4.1-ST-1 | Automated | `test_sales.py::test_fr4_1_st_1_search_to_sale_to_invoice_end_to_end` ; `fe:modules/sales/PosPage.test.tsx::Alt shortcuts focus search and complete a sale` |  |
| FR4.1-ST-2 | Automated | `test_sales.py::test_fr4_1_st_2_staff_cannot_record_sales_but_cashier_and_manager_can` |  |
| FR4.2-UT-1 | Automated | `test_returns.py::test_fr4_2_ut_1_valid_return_generates_credit_note` |  |
| FR4.2-UT-2 | Automated | `test_returns.py::test_fr4_2_ut_2_resaleable_unit_restocks_inventory` |  |
| FR4.2-UT-3 | Automated | `test_returns.py::test_fr4_2_ut_3_invoice_lookup_valid_and_invalid` |  |
| FR4.2-IT-1 | Automated | `test_returns.py::test_fr4_2_it_1_damaged_line_not_restocked_and_mixed_return` ; `test_constraints.py::test_damaged_return_cannot_be_restocked` |  |
| FR4.2-IT-2 | Automated | `test_returns.py::test_fr4_2_it_2_late_return_manager_override_and_lockout` |  |
| FR4.2-IT-3 | Automated | `test_returns.py::test_fr4_2_it_3_net_sales_data_aggregatable` ; `test_sales_trend.py::test_fr6_2_ut_1_and_it_1_sales_trend_ranks_and_nets_returns` | Return data and the report's net totals are covered |
| FR4.2-ST-1 | Automated | `test_returns.py::test_fr4_2_st_1_end_to_end_sale_to_return` ; `test_sales_trend.py::test_fr6_2_ut_1_and_it_1_sales_trend_ranks_and_nets_returns` ; `fe:modules/sales/ReturnsPage.test.tsx::result panel shows credit note number, refund total and restock status` | The API flow covers stock and report updates; the screen test covers the return form |
| FR4.2-ST-2 | Automated | `test_returns.py::test_authorization_and_location_scoping` |  |
| FR4.3-UT-1 | Automated | `test_invoices.py::test_fr4_3_ut_1_invoice_snapshot_is_available_with_the_sale` |  |
| FR4.3-UT-2 | Automated | `test_invoices.py::test_fr4_3_ut_2_sale_persists_required_invoice_snapshot` |  |
| FR4.3-UT-3 | Automated | `test_invoices.py::test_fr4_3_ut_3_two_item_invoice_total_is_lines_plus_gst` ; `test_invoices.py::test_fr4_3_ut_3_paise_are_rounded_per_line_and_still_add_up` |  |
| FR4.3-IT-1 | Automated | `test_invoices.py::test_fr4_3_it_1_reprint_after_catalog_edits_matches_the_original` ; `test_invoices.py::test_fr4_3_it_1_invoice_row_rejects_updates` |  |
| FR4.3-IT-2 | Automated | `test_invoices.py::test_fr4_3_it_2_partial_return_annotates_the_invoice_without_changing_the_records` |  |
| FR4.3-IT-3 | Automated | `test_invoices.py::test_fr4_3_it_3_history_finds_a_seven_year_old_sale_by_date_and_number` ; `test_invoices.py::test_fr4_3_it_3_invoice_near_the_end_of_retention_is_retrievable_in_full` ; `test_retention.py::test_retention_archive_dry_run_then_execute_is_verified_and_repeatable` |  |
| FR4.3-ST-1 | Automated | `test_invoices.py::test_fr4_3_st_1_twenty_parallel_cashiers_get_distinct_invoice_numbers` ; `test_constraints.py::test_invoice_numbers_unique_and_sequential` |  |
| FR4.3-ST-2 | Automated | `test_invoices.py::test_fr4_3_st_2_invoice_pdf_has_attachment_headers_and_snapshot_text` ; `test_invoices.py::test_fr4_3_st_2_long_invoice_spans_pages_and_credit_note_pdf_is_legible` | Print uses the browser's print dialog on the on-screen invoice; the PDF is checked here |

## 3.5 User Management

24 cases: 24 automated.

| ID | Status | Tests | Note |
|---|---|---|---|
| FR5.1-UT-1 | Automated | `test_users.py::test_admin_creates_manager_and_invite_is_not_exposed` |  |
| FR5.1-UT-2 | Automated | `test_rbac.py::test_role_permissions_match_the_matrix` ; `test_rbac.py::test_api_enforces_the_matrix_for_every_role` |  |
| FR5.1-UT-3 | Automated | `test_rbac.py::test_role_permissions_match_the_matrix` ; `test_rbac.py::test_api_enforces_the_matrix_for_every_role` |  |
| FR5.1-IT-1 | Automated | `test_rbac.py::test_role_change_applies_to_the_next_request` ; `test_users.py::test_role_change_applies_on_the_next_request` |  |
| FR5.1-IT-2 | Automated | `test_rbac.py::test_api_enforces_the_matrix_for_every_role` |  |
| FR5.1-IT-3 | Automated | `test_rbac.py::test_me_lists_the_role_permissions` ; `fe:shell/shell.test.tsx::the %s menu shows exactly its items` |  |
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
| FR5.3-ST-1 | Automated | `test_audit.py::test_mixed_activity_across_all_roles_is_in_the_trail_in_order` ; `test_audit.py::test_entries_from_every_module_share_one_structure` |  |
| FR5.3-ST-2 | Automated | `test_audit.py::test_only_admin_can_view_the_log` ; `fe:modules/audit/audit.test.tsx::a non-Admin is denied and the log is never requested` |  |

## 3.6 Reporting and Analytics

40 cases: 40 automated.

| ID | Status | Tests | Note |
|---|---|---|---|
| FR6.1-UT-1 | Automated | `test_reporting_stock.py::test_valuation_is_live_and_can_filter_location` ; `test_reporting_stock.py::test_valuation_uses_average_cost_then_active_supplier_catalog_price` |  |
| FR6.1-UT-2 | Automated | `test_reporting_stock.py::test_valuation_is_live_and_can_filter_location` ; `test_reporting_stock.py::test_valuation_uses_average_cost_then_active_supplier_catalog_price` |  |
| FR6.1-UT-3 | Automated | `test_plan_cases.py::test_fr6_1_ut_3_zero_stock_adds_no_value` |  |
| FR6.1-IT-1 | Automated | `test_plan_cases.py::test_fr2_4_it_2_adjustment_is_in_the_valuation_report` |  |
| FR6.1-IT-2 | Automated | `test_reporting_export.py::test_fr6_1_it_2_valuation_csv_and_pdf_carry_the_same_data_as_the_screen` |  |
| FR6.1-IT-3 | Automated | `test_reporting_stock.py::test_valuation_is_live_and_can_filter_location` |  |
| FR6.1-ST-1 | Automated | `test_reporting_stock.py::test_valuation_is_live_and_can_filter_location` ; `test_reporting_stock.py::test_staff_cannot_access_stock_reports` ; `test_reporting_stock.py::test_cashier_cannot_access_stock_reports` |  |
| FR6.1-ST-2 | Automated | `test_reporting_stock.py::test_staff_cannot_access_stock_reports` ; `test_reporting_stock.py::test_cashier_cannot_access_stock_reports` ; `test_rbac.py::test_api_enforces_the_matrix_for_every_role` |  |
| FR6.2-UT-1 | Automated | `test_sales_trend.py::test_fr6_2_ut_1_and_it_1_sales_trend_ranks_and_nets_returns` | Ranking and net totals are checked against known sale and return rows |
| FR6.2-UT-2 | Automated | `test_sales_trend.py::test_fr6_2_ut_1_and_it_1_sales_trend_ranks_and_nets_returns` | Zero-sales products are included and the limit is exercised by the response |
| FR6.2-UT-3 | Automated | `test_sales_trend.py::test_fr6_2_ut_3_sales_trend_rejects_invalid_ranges` | Invalid date ordering is rejected; boundary transaction coverage is in the report integration test |
| FR6.2-IT-1 | Automated | `test_sales_trend.py::test_fr6_2_ut_1_and_it_1_sales_trend_ranks_and_nets_returns` | Processed returns reduce net units and net amount |
| FR6.2-IT-2 | Automated | `test_sales_trend.py::test_fr6_2_it_2_unfiltered_report_is_the_sum_of_both_locations` |  |
| FR6.2-IT-3 | Automated | `test_sales_trend.py::test_fr6_2_it_3_csv_and_pdf_exports_match_the_on_screen_ranking` |  |
| FR6.2-ST-1 | Automated | `test_sales_trend.py::test_fr6_2_ut_1_and_it_1_sales_trend_ranks_and_nets_returns` | Report current stock is compared with seeded stock data |
| FR6.2-ST-2 | Automated | `test_reporting_export.py::test_fr6_5_st_1_export_is_denied_where_the_report_is_denied` ; `test_rbac.py::test_api_enforces_the_matrix_for_every_role` |  |
| FR6.3-UT-1 | Automated | `test_reporting_stock.py::test_reorder_report_filters_thresholds_and_uses_reorder_to` |  |
| FR6.3-UT-2 | Automated | `test_reporting_stock.py::test_reorder_report_filters_thresholds_and_uses_reorder_to` |  |
| FR6.3-UT-3 | Automated | `test_reporting_stock.py::test_reorder_report_filters_thresholds_and_uses_reorder_to` |  |
| FR6.3-IT-1 | Automated | `test_purchase_order_receiving.py::test_multiple_receipts_accumulate_and_short_items_remain_outstanding` | PO receipts are reflected through live stock |
| FR6.3-IT-2 | Automated | `test_notifications.py::test_alerts_are_location_scoped_and_align_with_reorder_report` |  |
| FR6.3-IT-3 | Automated | `test_reporting_stock.py::test_reorder_report_filters_thresholds_and_uses_reorder_to` |  |
| FR6.3-ST-1 | Automated | `fe:modules/reporting/LowStockReportPage.test.tsx::low-stock report filters locations and links a prefilled PO` ; `fe:modules/purchasing/PurchaseOrdersPage.test.tsx::reorder report links prefill a draft purchase order` |  |
| FR6.3-ST-2 | Automated | `test_reporting_stock.py::test_admin_can_access_reorder_report` ; `test_reporting_stock.py::test_staff_cannot_access_stock_reports` ; `test_reporting_stock.py::test_cashier_cannot_access_stock_reports` ; `test_rbac.py::test_api_enforces_the_matrix_for_every_role` |  |
| FR6.4-UT-1 | Automated | `test_supplier_performance.py::test_supplier_performance_calculates_four_of_five_on_time_once_per_po` | Counts one delivery per PO even when it has multiple receipts |
| FR6.4-UT-2 | Automated | `test_supplier_performance.py::test_supplier_performance_counts_orders_and_values_once_and_filters_by_period` | Order value is calculated once per PO despite multiple receipts |
| FR6.4-UT-3 | Automated | `test_supplier_performance.py::test_supplier_performance_price_trends_match_supplier_and_product_history` |  |
| FR6.4-IT-1 | Automated | `test_supplier_performance.py::test_supplier_performance_uses_only_accepted_receipts_and_reflects_receipt_updates` | Damaged quantities do not count as fulfilled stock |
| FR6.4-IT-2 | Automated | `test_supplier_performance.py::test_supplier_performance_price_trends_match_supplier_and_product_history` | Price points remain attributed to the supplier/product and history is unchanged |
| FR6.4-IT-3 | Automated | `test_supplier_performance.py::test_supplier_performance_uses_only_accepted_receipts_and_reflects_receipt_updates` ; `test_supplier_performance.py::test_supplier_performance_counts_orders_and_values_once_and_filters_by_period` | Tests receipt updates and selected-period filters |
| FR6.4-ST-1 | Automated | `fe:modules/reporting/SupplierPerformanceReportPage.test.tsx::renders supplier metrics and recorded product price changes side by side` ; `fe:modules/reporting/SupplierPerformanceReportPage.test.tsx::date and supplier filters request a side-by-side comparison for the selected suppliers` ; `fe:modules/reporting/SupplierPerformanceReportPage.test.tsx::shows loading, error and empty states` |  |
| FR6.4-ST-2 | Automated | `test_supplier_performance.py::test_supplier_performance_date_validation_and_manager_admin_access` ; `fe:shell/shell.test.tsx::staff and cashiers cannot see or directly open supplier performance reports` | Backend requires reports.view; the UI also hides and guards the route |
| FR6.5-UT-1 | Automated | `test_reporting_export.py::test_fr6_5_every_report_exports_in_both_formats` ; `test_reporting_export.py::test_fr6_5_csv_matches_the_on_screen_valuation` |  |
| FR6.5-UT-2 | Automated | `test_reporting_export.py::test_fr6_5_every_report_exports_in_both_formats` |  |
| FR6.5-UT-3 | Automated | `test_reporting_export.py::test_fr6_5_ut_3_commas_and_quotes_stay_in_one_cell` |  |
| FR6.5-IT-1 | Automated | `test_reporting_export.py::test_fr6_5_every_report_exports_in_both_formats` ; `test_reporting_export.py::test_supplier_performance_export_matches_the_on_screen_report` |  |
| FR6.5-IT-2 | Automated | `test_reporting_export.py::test_fr6_5_it_2_pdf_header_has_title_time_and_filter` |  |
| FR6.5-IT-3 | Automated | `test_reporting_export.py::test_fr6_5_it_3_five_thousand_rows_export_without_truncation` |  |
| FR6.5-ST-1 | Automated | `test_reporting_export.py::test_fr6_5_st_1_export_is_denied_where_the_report_is_denied` |  |
| FR6.5-ST-2 | Automated | `test_reporting_export.py::test_fr6_5_st_2_file_name_has_report_type_and_date` |  |

## 3.7 Search and Filter

16 cases: 14 automated, 2 manual.

| ID | Status | Tests | Note |
|---|---|---|---|
| FR7.1-UT-1 | Automated | `test_product_search.py::test_search_matches_name_sku_brand_variant_and_category` |  |
| FR7.1-UT-2 | Automated | `test_product_search.py::test_search_matches_name_sku_brand_variant_and_category` |  |
| FR7.1-UT-3 | Automated | `test_product_search.py::test_search_matches_name_sku_brand_variant_and_category` |  |
| FR7.1-IT-1 | Automated | `test_product_search.py::test_search_is_literal_live_and_location_scoped` |  |
| FR7.1-IT-2 | Automated | `test_product_search.py::test_search_matches_name_sku_brand_variant_and_category` |  |
| FR7.1-IT-3 | Automated | `test_product_search.py::test_search_matches_name_sku_brand_variant_and_category` | API returns an empty page; the empty-state text is in the screen tests |
| FR7.1-ST-1 | Manual |  | Timed by `scripts.loadtest` at 10,000 SKUs in the nightly `load-test` workflow, not in pytest; latest results in `docs/performance-results.md` |
| FR7.1-ST-2 | Automated | `test_product_search.py::test_search_requires_all_roles_and_rejects_long_terms` |  |
| FR7.2-UT-1 | Automated | `test_product_filters.py::test_category_and_price_range_return_exactly_the_intersection` |  |
| FR7.2-UT-2 | Automated | `test_product_filters.py::test_category_and_price_range_return_exactly_the_intersection` |  |
| FR7.2-UT-3 | Automated | `test_product_filters.py::test_price_and_stock_sorts_work_both_ways_on_live_data` |  |
| FR7.2-IT-1 | Automated | `test_product_filters.py::test_category_and_price_range_return_exactly_the_intersection` |  |
| FR7.2-IT-2 | Automated | `test_product_filters.py::test_price_and_stock_sorts_work_both_ways_on_live_data` |  |
| FR7.2-IT-3 | Automated | `test_product_filters.py::test_stock_status_filter_is_scoped_to_the_users_location` |  |
| FR7.2-ST-1 | Manual |  | Timed by `scripts.loadtest` at 10,000 SKUs in the nightly `load-test` workflow, not in pytest; latest results in `docs/performance-results.md` |
| FR7.2-ST-2 | Automated | `test_product_search.py::test_search_requires_all_roles_and_rejects_long_terms` ; `fe:modules/product/product.test.tsx::product filters and sort are sent with the search term` |  |

## 3.8 Notifications

16 cases: 16 automated.

| ID | Status | Tests | Note |
|---|---|---|---|
| FR8.1-UT-1 | Automated | `test_notifications.py::test_shared_stock_updates_create_distinct_alerts_and_clear_on_recovery` |  |
| FR8.1-UT-2 | Automated | `test_plan_cases.py::test_fr2_3_ut_3_and_fr8_1_ut_2_alert_only_at_or_below_threshold` |  |
| FR8.1-UT-3 | Automated | `test_notifications.py::test_notification_feed_is_recipient_scoped_and_chronological` ; `test_notifications.py::test_fr8_1_ut_3_a_notification_can_be_marked_read_and_dismissed` ; `test_notifications.py::test_mark_all_read_clears_the_unread_count` ; `fe:modules/notifications/notifications.test.tsx::the panel marks a notification read and dismisses another` | Notification list, mark read, mark all read, dismiss |
| FR8.1-IT-1 | Automated | `test_notifications.py::test_alerts_are_location_scoped_and_align_with_reorder_report` |  |
| FR8.1-IT-2 | Automated | `test_notifications.py::test_alerts_are_location_scoped_and_align_with_reorder_report` |  |
| FR8.1-IT-3 | Automated | `test_notifications.py::test_shared_stock_updates_create_distinct_alerts_and_clear_on_recovery` |  |
| FR8.1-ST-1 | Automated | `test_notifications.py::test_fr8_1_st_1_low_stock_notification_persists_across_sessions_until_acted_on` ; `fe:modules/notifications/notifications.test.tsx::the notifications page lists alerts and Create PO opens a prefilled draft` ; `fe:modules/notifications/notifications.test.tsx::the notifications page can show only unread notifications` | Notification bell panel and full page |
| FR8.1-ST-2 | Automated | `test_notifications.py::test_notification_feed_respects_role_permissions` ; `fe:shell/shell.test.tsx::the %s header notification bell: %s` |  |
| FR8.2-UT-1 | Automated | `test_purchase_orders.py::test_create_list_view_edit_and_submit_po_calculates_totals_and_audits` |  |
| FR8.2-UT-2 | Automated | `test_purchase_orders.py::test_receipt_hook_advances_lifecycle_notifies_and_freezes_lines` |  |
| FR8.2-UT-3 | Automated | `test_purchase_orders.py::test_create_list_view_edit_and_submit_po_calculates_totals_and_audits` |  |
| FR8.2-IT-1 | Automated | `test_purchase_orders.py::test_admin_creator_is_notified_of_po_status_changes` |  |
| FR8.2-IT-2 | Automated | `test_purchase_orders.py::test_cancelled_orders_are_excluded_from_pending_orders` |  |
| FR8.2-IT-3 | Automated | `test_purchase_order_lifecycle.py::test_fr8_2_it_3_status_changes_across_pos_are_listed_in_event_order` ; `test_notifications.py::test_notification_feed_is_recipient_scoped_and_chronological` |  |
| FR8.2-ST-1 | Automated | `test_purchase_order_lifecycle.py::test_fr8_2_st_1_manager_sees_the_full_po_notification_trail` |  |
| FR8.2-ST-2 | Automated | `test_purchase_order_lifecycle.py::test_fr8_2_st_2_po_status_notifications_are_not_shown_to_cashiers` ; `test_notifications.py::test_notification_feed_respects_role_permissions` ; `test_rbac.py::test_role_permissions_match_the_matrix` |  |

## 3.9 Security

10 cases: 10 automated.

| ID | Status | Tests | Note |
|---|---|---|---|
| SEC-AUTH-2-UT-1 | Automated | `test_auth.py::test_passwords_are_stored_as_salted_hashes` | Checks the Argon2id prefix |
| SEC-AUTH-2-UT-2 | Automated | `test_auth.py::test_passwords_are_stored_as_salted_hashes` |  |
| SEC-INP-2-IT-1 | Automated | `test_plan_cases.py::test_sec_inp_2_it_1_search_is_not_injectable` ; `test_product_search.py::test_search_is_literal_live_and_location_scoped` |  |
| SEC-INP-2-IT-2 | Automated | `test_plan_cases.py::test_sec_inp_2_it_2_filter_and_sort_parameters_are_not_injectable` |  |
| SEC-INP-3-IT-1 | Automated | `test_plan_cases.py::test_sec_inp_3_it_1_script_in_product_name_is_returned_as_data` ; `fe:security.test.tsx::the product list shows a script name literally` ; `fe:security.test.tsx::search results show a script name literally` ; `fe:security.test.tsx::the sales screen shows a script name literally in results and the cart` |  |
| SEC-INP-3-ST-1 | Automated | `fe:modules/audit/audit.test.tsx::logged text is shown as text, not markup` |  |
| SEC-SES-4-IT-1 | Automated | `test_csrf.py::test_sec_ses_4_it_1_request_without_token_is_rejected` |  |
| SEC-SES-4-IT-2 | Automated | `test_csrf.py::test_sec_ses_4_it_2_request_with_token_succeeds` ; `fe:api.test.ts` |  |
| SEC-DAT-6-ST-1 | Automated | `test_plan_cases.py::test_sec_dat_6_st_1_no_credentials_in_source` | CI's `secret-scan` job runs gitleaks over the full history on every pull request |
| SEC-DAT-6-ST-2 | Automated | `test_plan_cases.py::test_sec_dat_6_st_2_secrets_come_from_the_environment` |  |
