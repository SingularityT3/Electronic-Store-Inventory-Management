# Security requirement traceability

Maps each requirement of
[`Documents/Security_Requirements_Document_ESIMS.docx`](../Documents/Security_Requirements_Document_ESIMS.docx)
to the test plan cases and automated tests that cover it. The test plan labels cases by functional
requirement (for example `FR5.2-ST-1`), and only the five accepted derived requirements have `SEC-*` case IDs
(Appendix A.9). Every other security requirement is covered by functional cases or by tests that no plan
case cites, so this table is the way to go from a `SEC-*` ID to its evidence.

Results are in [`unit-test-report.md`](unit-test-report.md) (unit and integration cases) and
[`system-validation-report.md`](system-validation-report.md) (system cases). All tests named here pass in those
reports' runs. `fe:` is `frontend/src`; other paths are under `backend/tests`.

Cases whose ID starts with `SEC-` are the 10 Appendix A.9 cases: 7 unit/integration (in the unit test report)
and 3 system (in the system validation report).

## In-scope requirements

"Extra tests" are tests that no test plan case cites. They exercise the requirement but have no case ID.

### Authentication

| Requirement | Plan cases | Tests | Extra tests |
|---|---|---|---|
| SEC-AUTH-1 Login before any function | FR5.2-UT-3 | `test_auth.py::test_every_non_public_route_requires_a_session` | `test_auth.py::test_protected_endpoint_without_session_gets_401`, `test_rbac.py::test_signed_out_requests_get_401_not_403` |
| SEC-AUTH-2 Salted adaptive password hashes | **SEC-AUTH-2-UT-1, SEC-AUTH-2-UT-2**, FR5.2-IT-3 | `test_auth.py::test_passwords_are_stored_as_salted_hashes` (Argon2id prefix, different hashes for the same password), `test_auth.py::test_password_reset_flow` (the link contains neither the password nor its hash) | `test_users.py::test_admin_creates_manager_and_invite_is_not_exposed` |
| SEC-AUTH-3 Generic failed-login message | FR5.2-UT-2 | `test_auth.py::test_invalid_credentials_get_generic_error` | `test_auth.py::test_reset_request_does_not_reveal_accounts` |
| SEC-AUTH-4 Lockout after 5 failures | FR5.2-ST-2 | `test_auth.py::test_lockout_after_five_failures_blocks_correct_password` | `test_auth.py::test_admin_unlock_clears_lockout`, `test_auth.py::test_success_resets_failure_count`, `test_users.py::test_admin_unlocks_a_locked_account` |
| SEC-AUTH-5 Disabled accounts denied, deactivation ends sessions | none | none | `test_auth.py::test_deactivation_ends_active_sessions`, `test_auth.py::test_disabled_account_gets_status_message`, `test_users.py::test_deactivation_revokes_session_and_blocks_login` |
| SEC-AUTH-7 Single-use, time-limited reset | FR5.2-IT-3 | `test_auth.py::test_password_reset_flow` | `test_auth.py::test_reset_token_is_single_use`, `test_auth.py::test_reset_token_expires`, `test_auth.py::test_new_reset_link_spends_older_ones_when_used` |

### Session management

| Requirement | Plan cases | Tests | Extra tests |
|---|---|---|---|
| SEC-SES-1 Unpredictable, server-validated, cookie flags | none | none | `test_auth.py::test_session_cookie_is_httponly_secure_samesite`, `test_auth.py::test_forged_session_cookie_is_rejected` |
| SEC-SES-2 Idle and absolute expiry | FR5.2-IT-1 | `test_auth.py::test_idle_session_expires`, `fe:modules/auth/auth.test.tsx::a request rejected for an expired session sends the user to log in` | `test_auth.py::test_session_expires_after_absolute_lifetime`, `test_auth.py::test_activity_keeps_session_alive`, `test_auth.py::test_timeouts_are_configurable` |
| SEC-SES-3 Logout invalidates the session on the server | FR5.2-ST-1 | `test_auth.py::test_logout_invalidates_session_on_server` | |
| SEC-SES-4 CSRF protection | **SEC-SES-4-IT-1, SEC-SES-4-IT-2** | `test_csrf.py::test_sec_ses_4_it_1_request_without_token_is_rejected`, `test_csrf.py::test_sec_ses_4_it_2_request_with_token_succeeds`, `fe:api.test.ts` | `test_csrf.py::test_safe_requests_and_public_posts_need_no_token` |

### Authorization

| Requirement | Plan cases | Tests | Extra tests |
|---|---|---|---|
| SEC-AZ-1 RBAC, four roles, deny by default | FR5.1-UT-2, FR5.1-UT-3, FR5.1-ST-1 | `test_rbac.py::test_role_permissions_match_the_matrix`, `test_rbac.py::test_api_enforces_the_matrix_for_every_role` | `test_rbac.py::test_app_refuses_to_start_with_an_unguarded_route` |
| SEC-AZ-2 Server-side check on every request, 403 | FR5.1-IT-2, FR5.2-IT-2 | `test_rbac.py::test_api_enforces_the_matrix_for_every_role`, `test_rbac.py::test_per_action_check_within_a_screen` | |
| SEC-AZ-3 Only Admin manages users, no self role change | FR5.1-ST-2 | `test_users.py::test_non_admin_cannot_call_management_endpoints`, `fe:modules/auth/UsersPage.test.tsx::Manager opening users sees Access denied` | `test_users.py::test_last_admin_and_self_protection` (an Admin cannot demote themself) |
| SEC-AZ-5 Late returns need Manager override, logged | FR4.2-IT-2 | `test_returns.py::test_fr4_2_it_2_late_return_manager_override_and_lockout` | |
| SEC-AZ-6 Reports and exports limited to Manager/Admin | FR6.1-ST-2, FR6.2-ST-2, FR6.3-ST-2, FR6.5-ST-1 | `test_reporting_stock.py::test_staff_cannot_access_stock_reports`, `test_reporting_stock.py::test_cashier_cannot_access_stock_reports`, `test_reporting_export.py::test_fr6_5_st_1_export_is_denied_where_the_report_is_denied` | |
| SEC-AZ-7 Staff and Cashier scoped to their location | FR2.1-ST-2, FR5.1-ST-1 | `test_stock_levels.py::test_staff_stock_levels_are_scoped_to_assigned_location`, `test_rbac.py::test_staff_see_only_their_own_location` | `test_returns.py::test_authorization_and_location_scoping`, `test_notifications.py::test_alerts_are_location_scoped_and_align_with_reorder_report` |

### Audit and accountability

| Requirement | Plan cases | Tests | Extra tests |
|---|---|---|---|
| SEC-AUD-1 Log logins, failed logins, denials, every change | FR5.3-UT-1, FR5.3-UT-2, FR5.3-IT-1, FR5.3-IT-3, FR5.3-ST-1 | `test_audit.py::test_login_is_logged_with_user_and_time`, `test_audit.py::test_price_edit_is_logged_with_old_and_new_value`, `test_audit.py::test_entries_from_every_module_share_one_structure`, `test_rbac.py::test_denied_attempt_is_audited`, `test_audit.py::test_mixed_activity_across_all_roles_is_in_the_trail_in_order` | `test_auth.py::test_invalid_credentials_get_generic_error` (also asserts the `login_failed` entry) |
| SEC-AUD-2 Immutable trail, even for Admin | FR5.3-IT-2 | `test_audit.py::test_api_has_no_way_to_change_entries`, `test_audit.py::test_admin_cannot_edit_or_delete_an_entry`, `test_audit.py::test_database_rejects_changes_made_through_the_orm` | `test_constraints.py::test_audit_log_is_append_only` |
| SEC-AUD-3 Stock and price changes recorded, adjustment reason mandatory | FR2.4-UT-1, FR2.4-UT-2, FR2.4-IT-1 | `test_stock_adjustments.py::test_negative_adjustment_reduces_stock_and_logs_reason`, `test_stock_adjustments.py::test_blank_reason_is_rejected_and_stock_unchanged`, `test_audit.py::test_price_edit_is_logged_with_old_and_new_value` | `test_constraints.py::test_adjustment_requires_reason` |
| SEC-AUD-4 Audit log viewable by Admin only, filterable | FR5.3-UT-3, FR5.3-ST-2 | `test_audit.py::test_only_admin_can_view_the_log`, `test_audit.py::test_filter_by_user_any_case`, `fe:modules/audit/audit.test.tsx::a non-Admin is denied and the log is never requested` | `test_audit.py::test_filter_by_date_range`, `test_audit.py::test_filter_by_action_and_module` |

### Data protection and integrity

| Requirement | Plan cases | Tests | Extra tests |
|---|---|---|---|
| SEC-DAT-2 Atomic sale, no overselling | FR4.1-IT-2, FR4.1-ST-1 | `test_sales.py::test_fr4_1_it_2_two_concurrent_sales_of_the_last_unit_sell_it_once`, plus the 8-cashier run in the load test (NFR-2) | |
| SEC-DAT-3 Sales, returns and invoices retained and not editable | FR4.3-IT-1, FR4.3-IT-3 | `test_invoices.py::test_fr4_3_it_1_invoice_row_rejects_updates`, `test_invoices.py::test_fr4_3_it_3_history_finds_a_seven_year_old_sale_by_date_and_number` | `test_retention.py::test_sales_routes_have_no_delete_handlers_or_delete_statements`, `test_constraints.py::test_retention_blocks_truncate_for_all_sales_tables` |
| SEC-DAT-4 Supplier price history immutable | FR3.4-IT-2, FR3.4-ST-2 | `test_supplier_price_history.py::test_supplier_price_history_is_read_only_and_manager_admin_only`, `test_constraints.py::test_supplier_price_history_is_append_only` | |
| SEC-DAT-5 Backups and a tested restore | none | none | `test_backup.py::test_backup_contains_dump_images_and_checksums`, `test_backup.py::test_verify_detects_corruption`, `test_backup.py::test_restore_runs_pg_restore_and_unpacks_images` |
| SEC-DAT-6 Secrets kept out of source | **SEC-DAT-6-ST-1, SEC-DAT-6-ST-2** | `test_plan_cases.py::test_sec_dat_6_st_1_no_credentials_in_source`, `test_plan_cases.py::test_sec_dat_6_st_2_secrets_come_from_the_environment` | CI `secret-scan` job (gitleaks) |

### Input handling

| Requirement | Plan cases | Tests | Extra tests |
|---|---|---|---|
| SEC-INP-1 Server-side validation | FR1.1-UT-2, FR1.1-UT-3, FR1.2-UT-3 | `test_products.py::test_product_validation_rejects_duplicate_blank_and_negative`, `test_categories.py::test_admin_creates_tree_in_tree_order_and_invalid_parent_is_not_saved` | `test_users.py::test_required_fields_and_location_are_field_errors` |
| SEC-INP-2 Parameterized queries | **SEC-INP-2-IT-1, SEC-INP-2-IT-2** | `test_plan_cases.py::test_sec_inp_2_it_1_search_is_not_injectable`, `test_plan_cases.py::test_sec_inp_2_it_2_filter_and_sort_parameters_are_not_injectable` | |
| SEC-INP-3 Output encoding (XSS) | **SEC-INP-3-IT-1, SEC-INP-3-ST-1** | `test_plan_cases.py::test_sec_inp_3_it_1_script_in_product_name_is_returned_as_data`, `fe:security.test.tsx` (product list, search results, sales screen), `fe:modules/audit/audit.test.tsx::logged text is shown as text, not markup` | |
| SEC-INP-6 No circular categories, no negative stock | FR1.2-IT-1, FR2.4-IT-3 | `test_categories.py::test_cycles_duplicates_delete_and_rollup_counts`, `test_stock_adjustments.py::test_adjustment_below_zero_is_blocked` | `test_constraints.py::test_category_cannot_be_its_own_parent`, `test_constraints.py::test_negative_stock_rejected` |

## Gaps

- **SEC-DAT-5 asks for encrypted backups.** The tests above check the backup contents, checksum
  verification, restore and failure alerts. Nothing in the tests or in `docs/backup-recovery.md` mentions
  encrypting a backup, so that part of the requirement is not evidenced. Access restriction is not tested either.
- **SEC-AUTH-2 also says passwords are never logged or returned by any API.** The tests show they are hashed
  and absent from the reset link and the invite response. No test searches the logs or every response for a
  password.
- **SEC-AUTH-5, SEC-SES-1 and SEC-DAT-5 have no plan case at all.** They are tested only by the extra tests
  listed. The plan itself is unchanged, since the test plan is a reviewed document.

## Out-of-scope requirements

The Security Requirements Document (section 7) marks these "Derived - out of scope", so no test cases exist
for them: SEC-AUTH-6, SEC-AZ-4, SEC-AUD-5, SEC-AUD-6, SEC-DAT-1, SEC-DAT-7, SEC-INP-4, SEC-INP-5,
SEC-OPS-1 to SEC-OPS-6. Some behaviour exists anyway (`test_users.py::test_last_admin_and_self_protection`
blocks deactivating or demoting the last Admin), but it is not a requirement of this project.
