# Code coverage report

Statement (line) and function coverage from the final test run. Branch coverage has its own report:
[`branch-coverage-report.md`](branch-coverage-report.md). Test results are in
[`unit-test-report.md`](unit-test-report.md).

Coverage was measured over the full suite run (355 backend and 137 frontend tests, all passing).
The project sets no coverage target, so this report records the numbers and points out the gaps; it does not
grade them pass or fail.

## Summary

| Code base | Statements | Covered | Missed | Statement / line coverage | Function coverage |
|---|---:|---:|---:|---:|---:|
| Backend (`backend/app`, Python) | 5205 | 4705 | 500 | **90.4%** | not reported by coverage.py |
| Frontend (`frontend/src`, TypeScript) | 8070 | 6284 | 1786 | **77.9%** | **71.2%** (421/591) |

Environment and commands:

- Run date: 2026-11-06
- Backend: Python 3.13.18, pytest 8.3.4, coverage.py 7.17.2 (via pytest-cov), PostgreSQL 16.15
- Frontend: Node 22.23.4, Vitest 3.2.7 (jsdom), @vitest/coverage-v8 3.2.7
- Code under test: `main` at commit `b769635` (merge of pull request #90), unmodified

Docker was not available in the session that produced these numbers, so the suites ran directly
on the host (a Python virtual environment with `backend/requirements-dev.txt`, a local PostgreSQL 16
server, and `npm ci` for the frontend) instead of in the project's containers. The containers use
Python 3.12 and `postgres:16-alpine`. The tests create their own throwaway databases, so the
method is the same, but the interpreter and database build differ slightly from the CI images.

```bash
# backend
docker compose run --rm backend sh -c "pip install -q pytest-cov && pytest --cov=app --cov-branch --cov-report=term-missing"
# frontend
docker compose run --rm --no-deps frontend sh -c "npm install --no-save @vitest/coverage-v8@3.2.7 && npx vitest run --coverage --coverage.provider=v8 --coverage.all --coverage.include='src/**/*.{ts,tsx}' --coverage.exclude='src/**/*.test.*' --coverage.exclude='src/test-setup.ts'"
```

coverage.py's own headline figure (87% in `--cov-report=term`) merges statements and branches into one number; the table
above splits them. Neither coverage tool is a project dependency, so both are installed on the fly. The frontend run counts every
source file, including ones no test imports (`--coverage.all`), otherwise untested pages would be left out of the
percentage. Only `backend/app` is measured on the backend; `tests/`, `scripts/` and `migrations/` are not.

## Backend

28 of 50 source files are fully covered.

| Module | Files | Statements | Covered | Missed | Coverage |
|---|---:|---:|---:|---:|---:|
| app (core) | 7 | 130 | 122 | 8 | 93.8% |
| audit | 6 | 157 | 157 | 0 | 100.0% |
| auth | 15 | 657 | 614 | 43 | 93.5% |
| notifications | 6 | 292 | 280 | 12 | 95.9% |
| product | 5 | 745 | 573 | 172 | 76.9% |
| purchasing | 6 | 779 | 714 | 65 | 91.7% |
| reporting | 5 | 487 | 474 | 13 | 97.3% |
| sales | 6 | 1182 | 1077 | 105 | 91.1% |
| stock | 5 | 776 | 694 | 82 | 89.4% |
| **Total** | 50 | 5205 | 4705 | 500 | **90.4%** |

Files with missed statements, lowest coverage first:

| File | Statements | Covered | Missed | Coverage |
|---|---:|---:|---:|---:|
| `app/modules/auth/_internal/mail.py` | 23 | 9 | 14 | 39.1% |
| `app/modules/product/router.py` | 606 | 437 | 169 | 72.1% |
| `app/db.py` | 21 | 17 | 4 | 81.0% |
| `app/modules/stock/service.py` | 432 | 367 | 65 | 85.0% |
| `app/modules/sales/service.py` | 548 | 478 | 70 | 87.2% |
| `app/modules/purchasing/router.py` | 270 | 240 | 30 | 88.9% |
| `app/modules/notifications/_internal/service.py` | 130 | 118 | 12 | 90.8% |
| `app/modules/auth/router.py` | 273 | 249 | 24 | 91.2% |
| `app/modules/purchasing/purchase_orders.py` | 346 | 316 | 30 | 91.3% |
| `app/main.py` | 54 | 50 | 4 | 92.6% |
| `app/modules/stock/router.py` | 245 | 228 | 17 | 93.1% |
| `app/modules/sales/router.py` | 433 | 403 | 30 | 93.1% |
| `app/modules/auth/_internal/users.py` | 15 | 14 | 1 | 93.3% |
| `app/modules/purchasing/service.py` | 76 | 71 | 5 | 93.4% |
| `app/modules/sales/documents.py` | 102 | 97 | 5 | 95.1% |
| `app/modules/reporting/router.py` | 187 | 178 | 9 | 95.2% |
| `app/modules/product/service.py` | 79 | 76 | 3 | 96.2% |
| `app/modules/auth/service.py` | 72 | 70 | 2 | 97.2% |
| `app/modules/auth/_internal/reset.py` | 43 | 42 | 1 | 97.7% |
| `app/modules/reporting/_internal/export.py` | 104 | 102 | 2 | 98.1% |
| `app/modules/auth/_internal/permissions.py` | 53 | 52 | 1 | 98.1% |
| `app/modules/reporting/service.py` | 194 | 192 | 2 | 99.0% |

### Main uncovered areas

- **Product router (`product/router.py`, 72.1%).** The update and delete handlers for categories (`update_category`, `delete_category`),
  category attributes (create, update and delete), variant update (`update_variant`) and product image delete (`delete_image`) are not
  reached by any test. Create, list, search, filter and the other paths are covered.
- **Password reset email (`auth/_internal/mail.py`, 39.1%).** The SMTP delivery code (message build, STARTTLS, login, send, error logging)
  is never run; tests replace the sender. The "SMTP not configured" path is covered.
- **Sales and stock services.** The misses are validation and error branches: return handling (`process_return`, unknown sale line,
  quantity below 1, invalid condition), line and payment checks when recording a sale, stock adjustment (`adjust_stock`), and receiving,
  consuming and moving batch- and serial-tracked stock.
- **Request logging and database session (`main.py`, `db.py`).** The path that logs an unhandled exception and the cached engine and
  session factories (the tests build their own engines).

## Frontend

77.86% of statements and 71.23% of functions are covered. Lines match statements in the v8 provider.

| Area (`frontend/src/...`) | Statements | Functions | Lines | Covered / total statements |
|---|---:|---:|---:|---:|
| src (root) | 89.3% | 83.3% | 89.3% | 225/252 |
| modules/audit | 93.7% | 75.0% | 93.7% | 192/205 |
| modules/auth | 67.2% | 73.3% | 67.2% | 344/512 |
| modules/notifications | 79.5% | 72.9% | 79.5% | 542/682 |
| modules/product | 45.6% | 37.7% | 45.6% | 566/1242 |
| modules/purchasing | 88.0% | 82.0% | 88.0% | 1227/1395 |
| modules/reporting | 69.0% | 84.1% | 69.0% | 493/715 |
| modules/sales | 80.5% | 58.4% | 80.5% | 1261/1567 |
| modules/stock | 94.8% | 93.7% | 94.8% | 849/896 |
| shell | 98.0% | 93.3% | 98.0% | 335/342 |
| shell/components | 97.5% | 92.3% | 97.5% | 234/240 |
| utils | 72.7% | 100.0% | 72.7% | 16/22 |
| **Total** | **77.9%** | **71.2%** | **77.9%** | **6284/8070** |

All files, lowest line coverage first:

| File | Covered / total statements | Lines | Functions |
|---|---:|---:|---:|
| `src/main.tsx` | 0/15 | 0% | 0% |
| `src/modules/product/ProductViewPage.tsx` | 7/288 | 2.43% | 0% |
| `src/modules/product/CategoryAttributesPage.tsx` | 5/133 | 3.75% | 0% |
| `src/modules/reporting/SalesTrendReportPage.tsx` | 9/219 | 4.1% | 0% |
| `src/modules/auth/ResetPasswordPage.tsx` | 4/62 | 6.45% | 0% |
| `src/modules/auth/ForgotPasswordPage.tsx` | 3/45 | 6.66% | 0% |
| `src/shell/PlaceholderPage.tsx` | 1/8 | 12.5% | 0% |
| `src/modules/product/ProductFormPage.tsx` | 121/224 | 54.01% | 42.85% |
| `src/modules/sales/DocumentPages.tsx` | 133/245 | 54.28% | 10.52% |
| `src/modules/product/CategoriesPage.tsx` | 104/188 | 55.31% | 13.04% |
| `src/modules/product/api.ts` | 31/52 | 59.61% | 9.09% |
| `src/modules/sales/AvailabilityPage.tsx` | 68/104 | 65.38% | 85.71% |
| `src/modules/notifications/useNotifications.ts` | 100/145 | 68.96% | 60% |
| `src/utils/date.ts` | 16/22 | 72.72% | 100% |
| `src/modules/notifications/NotificationsPage.tsx` | 194/258 | 75.19% | 71.42% |
| `src/modules/auth/UsersPage.tsx` | 225/293 | 76.79% | 70.58% |
| `src/modules/product/ProductListPage.tsx` | 106/136 | 77.94% | 56.25% |
| `src/modules/product/ProductSearchPage.tsx` | 83/104 | 79.8% | 76.92% |
| `src/modules/purchasing/POReceivingPage.tsx` | 240/290 | 82.75% | 76.66% |
| `src/modules/sales/PosPage.tsx` | 390/458 | 85.15% | 53.84% |
| `src/api.ts` | 71/83 | 85.54% | 100% |
| `src/modules/sales/ReturnsPage.tsx` | 489/571 | 85.63% | 84% |
| `src/modules/notifications/NotificationPanel.tsx` | 195/223 | 87.44% | 71.42% |
| `src/modules/purchasing/PurchaseOrdersPage.tsx` | 489/555 | 88.1% | 80.55% |
| `src/modules/purchasing/SuppliersPage.tsx` | 333/372 | 89.51% | 86.48% |
| `src/modules/notifications/links.ts` | 27/30 | 90% | 100% |
| `src/modules/stock/StockTransferPage.tsx` | 223/244 | 91.39% | 100% |
| `src/modules/purchasing/SupplierPriceHistoryPage.tsx` | 120/130 | 92.3% | 100% |
| `src/modules/product/ProductFilters.tsx` | 103/111 | 92.79% | 87.5% |
| `src/modules/purchasing/api.ts` | 41/44 | 93.18% | 72.22% |
| `src/modules/audit/AuditLogPage.tsx` | 191/204 | 93.62% | 75% |
| `src/shell/components/SearchBox.tsx` | 45/48 | 93.75% | 80% |
| `src/shell/components/Breadcrumb.tsx` | 16/17 | 94.11% | 100% |
| `src/modules/sales/api.ts` | 17/18 | 94.44% | 62.5% |
| `src/modules/reporting/SupplierPerformanceReportPage.tsx` | 221/232 | 95.25% | 86.66% |
| `src/modules/sales/DocumentView.tsx` | 159/166 | 95.78% | 100% |
| `src/modules/stock/StockLevelsPage.tsx` | 357/372 | 95.96% | 93.75% |
| `src/modules/stock/BatchRecallPage.tsx` | 120/125 | 96% | 100% |
| `src/modules/stock/LocationsPage.tsx` | 145/151 | 96.02% | 85% |
| `src/shell/components/ConfirmDialog.tsx` | 74/76 | 97.36% | 100% |
| `src/modules/reporting/StockValuationPage.tsx` | 146/147 | 99.31% | 92.3% |
| `src/App.tsx` | 154/154 | 100% | 100% |
| `src/modules/audit/index.ts` | 1/1 | 100% | 100% |
| `src/modules/auth/AuthContext.tsx` | 35/35 | 100% | 100% |
| `src/modules/auth/LoginPage.tsx` | 62/62 | 100% | 100% |
| `src/modules/auth/RequireAuth.tsx` | 9/9 | 100% | 100% |
| `src/modules/auth/index.ts` | 6/6 | 100% | 100% |
| `src/modules/notifications/api.ts` | 22/22 | 100% | 83.33% |
| `src/modules/notifications/index.ts` | 4/4 | 100% | 100% |
| `src/modules/product/index.ts` | 6/6 | 100% | 100% |
| `src/modules/purchasing/index.ts` | 4/4 | 100% | 100% |
| `src/modules/reporting/LowStockReportPage.tsx` | 113/113 | 100% | 100% |
| `src/modules/reporting/index.ts` | 4/4 | 100% | 100% |
| `src/modules/sales/index.ts` | 5/5 | 100% | 100% |
| `src/modules/stock/index.ts` | 4/4 | 100% | 100% |
| `src/shell/AppLayout.tsx` | 27/27 | 100% | 100% |
| `src/shell/DashboardPage.tsx` | 37/37 | 100% | 100% |
| `src/shell/NotFoundPage.tsx` | 10/10 | 100% | 100% |
| `src/shell/NotificationBell.tsx` | 10/10 | 100% | 100% |
| `src/shell/Sidebar.tsx` | 25/25 | 100% | 100% |
| `src/shell/UserMenu.tsx` | 40/40 | 100% | 100% |
| `src/shell/index.ts` | 5/5 | 100% | 100% |
| `src/shell/navigation.ts` | 158/158 | 100% | 100% |
| `src/shell/usePopover.ts` | 22/22 | 100% | 100% |
| `src/shell/components/AccessDenied.tsx` | 13/13 | 100% | 100% |
| `src/shell/components/DataTable.tsx` | 32/32 | 100% | 100% |
| `src/shell/components/EmptyState.tsx` | 11/11 | 100% | 100% |
| `src/shell/components/FormField.tsx` | 24/24 | 100% | 100% |
| `src/shell/components/RequirePermission.tsx` | 11/11 | 100% | 100% |
| `src/shell/components/index.ts` | 8/8 | 100% | 100% |

### Main uncovered areas

- `src/main.tsx`
- `src/modules/auth/ForgotPasswordPage.tsx`
- `src/modules/auth/ResetPasswordPage.tsx`
- `src/modules/product/CategoryAttributesPage.tsx`
- `src/modules/product/ProductViewPage.tsx`
- `src/modules/reporting/SalesTrendReportPage.tsx`
- `src/shell/PlaceholderPage.tsx`

These seven files are below 30% line coverage. `ForgotPasswordPage`, `ResetPasswordPage`, `CategoryAttributesPage`,
`ProductViewPage` and `SalesTrendReportPage` have no component test. `main.tsx` is the entry point and `PlaceholderPage` is a
stand-in screen. The backend behind the password reset and sales trend screens is tested (`test_auth.py`, `test_sales_trend.py`),
so those two gaps are in the screens only. The category attribute update and delete handlers are untested on both sides
(see Backend above).

## Reading these numbers

- Coverage shows which code ran during the tests, not that every outcome was checked. The functional evidence is the 226-case plan
  in [`unit-test-report.md`](unit-test-report.md) and [`system-validation-report.md`](system-validation-report.md).
- The backend and frontend figures come from different tools and cannot be added together.
