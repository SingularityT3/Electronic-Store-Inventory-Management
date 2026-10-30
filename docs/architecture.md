# Architecture

ESIMS is a modular monolith: one FastAPI backend, one React (Vite, TypeScript) frontend, one
PostgreSQL database. It follows the component diagram in `Documents/esims_component_diagram.png`
and SRS NFR-11 (separate product, stock, sales and reporting concerns).

## Modules (`backend/app/modules/`)

| Module          | Responsibility                                                          |
| --------------- | ----------------------------------------------------------------------- |
| `product`       | Catalog, hierarchical categories, variants, search/filter, product images |
| `stock`         | Per-location stock, movements, adjustments, transfers, batches/serials  |
| `sales`         | Sales transactions, returns, invoices                                   |
| `reporting`     | Valuation, trend, reorder and supplier reports, CSV/PDF export          |
| `auth`          | Authentication, sessions, users and RBAC                                |
| `purchasing`    | Suppliers, purchase orders, receiving, supplier price history           |
| `notifications` | In-app low-stock and order status notifications                         |
| `audit`         | Immutable audit log                                                     |

Each module has the same shape:

- `__init__.py` re-exports the public service interface. This is all other modules may import.
- `service.py` is the public service interface (a `Protocol`; implementations live in `_internal`).
- `router.py` holds the module's HTTP routes, mounted under `/api/<module>` by `app/main.py`.
- `_internal/` holds models, repositories and implementation. It is private to the module.

## Rules

1. A module never imports another module's `_internal` package and never touches another
   module's tables. It calls the other module's service interface.
2. Dependencies point downward only (a module may import modules below it, never above):

   ```
   reporting
   sales | purchasing     (independent of each other)
   stock
   product
   notifications
   auth
   audit
   ```

   This order follows the component diagram: sales and purchasing update stock, reporting reads
   everything, and every module validates sessions (`auth`) and logs activity (`audit`).
   It also guarantees there are no circular dependencies.
3. Where a lower module must react to a higher one (for example stock raising a low-stock
   alert), it does so through a lower module's interface (`notifications`).

Rules 1 and 2 are enforced by [import-linter](https://import-linter.readthedocs.io) contracts in
`backend/pyproject.toml`, run as part of the test suite (`tests/test_architecture.py`). Changing
the layer order means editing that file and this document together.

## Database

Each module owns its tables, defined in `_internal/models.py`. Rule 1 applies to them: no other
module reads or writes them. Foreign keys across modules follow rule 2 and point downward only.
A reference to a higher module's table is a plain ID column (e.g. `users.location_id`, since
`stock` owns locations). Migrations are in `backend/migrations/` (Alembic). Ownership, the
ER diagram and the rules enforced in the database are in [`schema.md`](schema.md).

## Authentication

Sessions are server-side (`user_sessions`): the browser holds a random token in an HttpOnly,
SameSite=Strict cookie, and every request checks it against the idle timeout, the absolute
lifetime and the account status (SRS A-12). `app/main.py` mounts every module router with the
`current_user` dependency from `app.modules.auth`, so new routes require a signed-in user by
default. Only `/api/health` and the login, logout and password reset routes are public.

## Authorization (RBAC)

Every route declares what it needs, and the server enforces it whatever the UI shows
(FR-5.1, NFR-7, SEC-AZ-1/2). `app.modules.auth` exports:

- `Permission`, the capabilities (`products.manage`, `stock.adjust`, ...). Which role holds
  which is the matrix `ROLE_PERMISSIONS` in `auth/_internal/permissions.py` (SRS 2.3, A-5,
  A-6, A-10). Admin holds all of them.
- `require(Permission.X)`, a dependency for a route or a router. It gives the route the
  signed-in user, or responds 403 and writes an `unauthorized_access_attempt` audit entry
  ("Unauthorized Access Attempt", FR-5.3). A route that needs the user takes
  `user: Annotated[CurrentUser, Depends(require(Permission.X))]`.
- `signed_in`, the same for self-service routes open to every role (`/auth/me`).
- `authorize(db, user, permission, "what")` for a check partway through a route, such as a
  price change in a product edit (FR5.2-IT-2), and `authorize_location(db, user, location_id,
  "what")` for SRS A-9: Staff and Cashier act on their own location only. Both deny the same
  way, rolling back what the request changed so far.

Access is denied by default: `create_app` calls `ensure_routes_authorized`, which refuses to
start the app if a route outside `PUBLIC_PATHS` (`app/main.py`) has neither `require(...)` nor
`signed_in`. The role is read from the database on every request, so a role change applies to
the user's next request. `/auth/me` and the login response list the user's `permissions`; the
frontend's `can(user, permission)` uses them to hide what the role cannot do, and its
`Permission` type must be kept in step with the backend enum.

## Audit log

Modules write audit entries with `audit_service.record(db, ...)` from `app.modules.audit`, in
the same transaction as the change they describe (FR-5.3, SEC-AUD-1). Every entry has the same
fields: user, timestamp, module, action, the record it concerns, details, and `before`/`after`
values. For an edit, `changes(old, new)` reduces two snapshots to the fields that changed, e.g.
`({"price": "28999.00"}, {"price": "26999.00"})`. Values may be Decimals, dates or enums;
they are stored as JSON strings. Never log passwords or tokens.

Actions are snake_case verbs in the past tense, named after the record (`product_price_updated`,
`stock_adjusted`, `po_created`); the viewer shows them as "Product price updated".

The log is append-only (NFR-8, SEC-AUD-2): no service method or route edits or deletes an
entry, for any role, and the `reject_modification` trigger rejects `UPDATE`, `DELETE` and
`TRUNCATE` in the database. Admins read it at `/audit` in the frontend, through
`GET /api/audit/entries` (filters: `username`, `action`, `module`, `since`, `until`; newest first,
paged) and `GET /api/audit/filters`. `app/main.py` mounts the audit router behind
`require(Permission.AUDIT_VIEW)`, because `audit` sits below `auth` and cannot import it
(SEC-AUD-4).

## Configuration

All settings come from environment variables (`backend/app/config.py`), with `ENV` selecting
`dev`, `test` or `prod`. `.env.example` lists the variables; the real `.env` is git-ignored.

## Frontend

`frontend/src/modules/` mirrors the backend modules. In development, Vite proxies `/api` to the
backend.

`frontend/src/shell/` is the desktop UI shell (NFR-9, NFR-10) that every signed-in screen renders
in: a header (brand, notification bell placeholder, user menu with Sign out), a sidebar menu and
the content area, plus shared components in `shell/components/` (`DataTable`, `FormField`,
`EmptyState`, `ConfirmDialog`, `AccessDenied`, `RequirePermission`).

### Product search

`GET /api/product` accepts the optional `q` parameter in addition to its existing paging
parameters. A trimmed term searches active product names, SKUs (including active variant SKUs),
brands and category names. Category matches roll up to every descendant category through the
same recursive tree query used by the category product endpoint. Terms are literal: backslashes,
percent signs and underscores are escaped before being passed as bound parameters; terms longer
than 100 characters are rejected. Results are ranked by exact SKU, exact name, prefix matches
and then other substring matches, with name and ID as stable tie-breakers.

Search results include the category path, current price, active variant count and live stock.
The product module receives one batched stock request through its public `StockCheck` protocol;
Staff and Cashier requests are scoped to their assigned location, while Admin and Manager see
the total across locations. Search responses are never cached (`Cache-Control: no-store`) and
reads do not create audit entries. The frontend `SearchBox` is reusable by future stock,
purchasing and sales screens; the current implementation mounts it on the product list and
product search screens only.

The same paged endpoint filters and sorts (FR-7.2, #13): `category_id` (including its
subcategories), `min_price`/`max_price`, `stock_status` (`in_stock`, `low_stock`,
`out_of_stock`), and `sort` (`relevance`, `name`, `price`, `stock`) with `order` (`asc`,
`desc`). Filters combine with each other and with `q`; without `sort` a search is ordered by
relevance and a plain listing by name. Stock and its filter and sort use the same scope as the
stock column. A product is out of stock at zero, and low when it has an active low/out-of-stock
alert in that scope (its stock is at or below a location's reorder threshold, FR-2.3). Price
filters and sorts run in SQL; a stock filter or sort reads the stock of every matching product
in one batched call and pages in Python. The frontend `ProductFilters` component sits under the
search box on the product list and product search screens. The 5,000/10,000-product performance benchmark belongs
to #35; it was not run in this change because the benchmark fixture and production-sized catalog
are not part of the current test suite.

The menu is built from `NAV_ITEMS` in `shell/navigation.ts`: each item names the permission it
needs, and the sidebar shows an item only if the server-sent `permissions` of the signed-in user
include it, so each role sees exactly its screens (FR5.1-IT-3). Menu hiding is cosmetic. Every
item's route, and any sub-route under it, is also wrapped in `RequirePermission`, which shows the
access-denied page for a URL typed by hand; the API enforces the same rule with a 403 (NFR-7).

To add a screen, give its feature module a page component and replace the `PlaceholderPage` for
its path in `App.tsx`. A new menu item is one entry in `NAV_ITEMS`.

## Sales transaction recording

The sales module exposes `POST /api/sales` for the cashier POS, `GET /api/sales/{id}` for receipt data,
`GET /api/sales/by-invoice/{invoice_number}` for invoice lookup, `POST /api/sales/returns` for processing
returns, and `GET /api/sales/returns/{return_id}` for credit note data. Checkout validates live catalog prices and active
variants, merges duplicate items, sorts them by `(product_id, variant_id)`, and calls the stock
module's row-locked `update_stock` operation in one database transaction. The sale, stock
movements, payments, invoice and one `sale_recorded` audit entry commit together or roll back
together. A zero balance reports `Out of stock`; a partial balance reports `Insufficient stock`,
with all failing lines returned in one 409 response.

GST is configured by `GST_RATE` (18% by default) and is applied after each line discount. Values
are rounded half up to two decimals per line and totals are sums of stored line values. A discount
is either a fixed amount or a percentage from 0 through 100 and cannot exceed the gross line
amount. A nullable unique idempotency key makes a retry safe for the same user and location.

Customer returns (`POST /api/sales/returns`) run in one atomic database transaction:
1. Concurrency: takes a row lock (`SELECT ... FOR UPDATE`) on the `sales` record to serialise parallel returns
   and verify remaining returnable quantities against actual sold quantities.
2. Return window & Manager override: sales within `RETURN_WINDOW_DAYS` (default 30 calendar days, evaluated in UTC)
   are accepted without approval. Sales older than 30 days require Manager approval (SRS A-1, A-11). If the processor
   holds `RETURNS_APPROVE_LATE` (Manager or Admin), the return is self-approved. Otherwise, the processor provides
   the Manager's credentials in `manager_approval`. The auth module's public `verify_override(db, username, password, permission)`
   verifies the approving user using `authenticate()`, preserving lockout counting (SRS A-12), dummy-hash timing attack
   protection, and denial auditing without starting a new session. Failed override attempts record a generic error
   (`"Manager approval failed."`) and persist lockout counts across request rollbacks.
3. Refund allocation: proportional share of the original `line_total` (including tax and discounts) using
   `ROUND_HALF_UP` to two decimal places:
   `round(line_total * (already_returned + now_returned) / sold) - round(line_total * already_returned / sold)`.
   Cumulative line refunds over multiple returns add up exactly to the original line total.
4. Condition & Restocking:
   - Resaleable: untracked items increase stock via `update_stock(movement_type="return")` at the original sale's location.
     Serial-tracked items restore units via `restore_returned_serials` and batch-tracked units restore quantity via
     `restore_returned_batch_units`. Units remain linked to the original sale line.
   - Damaged: items are recorded in `return_lines` with `condition="damaged"` and `restocked=False`, routing them to a
     non-sellable state without modifying stock levels or sellable stock movements.
   - Deleted items: if a product or variant was deactivated since the sale, return and refund are recorded with
     `restocked=False` instead of failing.
5. Return status: `return_status` is computed dynamically on read ("none", "partially_returned", "fully_returned")
   without modifying `sales`, `sale_lines` or `invoices` tables.
6. Credit note data: credit note number format `CN-<return_id>` zero-padded. Audit entries `return_processed` and
   (for late returns) `return_late_approved` are recorded atomically.

Invoice and credit note PDF/printable layout is described in #26 below; retention and delete
protection remains #27, and sales trend report netting remains #31 (net sales subtract
`return_lines.refund_amount`).

## Invoices and receipts (#26)

`record_sale` allocates the invoice number from PostgreSQL's `invoice_number_seq` and writes the
invoice with the sale in one transaction. `invoice_label(n)` is the only display formatter:
`INV-0007`, `INV-12345`; the lookup parser continues to accept either the bare number or the
`INV-` prefix. PostgreSQL sequences are concurrent-safe and are not gapless: a rolled-back sale
can consume a number, and that gap is retained.

Each invoice stores a versioned JSONB `content` snapshot when created. It includes store settings,
location and cashier labels, customer, GST rate, line and tracking labels, payments and all money
totals. Before insertion, the service checks line-total sum, invoice/sale total equality and
`subtotal - discount + tax = total`; a mismatch aborts the entire sale. A database trigger rejects
every invoice update. Return rows likewise receive a versioned `content` snapshot inside the return
transaction; `get_credit_note` reads this snapshot so later catalog edits cannot rewrite a receipt.
The return trigger permits the initial `{}` to snapshot write and rejects later content changes.

Both snapshots feed one `Document` model and one A4 portrait fpdf2 renderer in `sales`. Core
Helvetica fonts use Latin-1; the rupee symbol is rendered as `Rs `, matching reporting exports.
The PDF records the snapshot issue/return date as its creation date; text and document data are
stable on re-render (PDF bytes are not promised byte-identical). Table headers repeat on page breaks,
long item names wrap, amounts align to the right and each page is numbered.

`GET /api/sales/history` provides scoped, filterable paging without a date cutoff.
`GET /api/sales/invoices/{invoice_number}` returns the stored content plus live return status and
credit-note summaries. PDF exports are at `/api/sales/invoices/{invoice_number}/pdf` and
`/api/sales/returns/{return_id}/pdf`; successful exports are audited. Return status is an annotation
(`Partially Returned` or `Fully Returned`) and never changes the original invoice snapshot.
  Retention and deletion policy is enforced by migration 0013; the app has no invoice delete path.

## Transaction retention (#27)

Sales, returns, invoices, and their child/link records are retained at least eight calendar years. Database triggers block early row deletion, all truncation, and changes to clock dates; `RETENTION_YEARS` may raise the policy for the operator archive tool. The database trigger floor is eight years. `scripts.retention` reports and archives expired sale bundles after backup verification; archiving is operator-only. Full database backups include these records and must be retained at least `RETENTION_YEARS x 12` months. See [`retention.md`](retention.md).

## Product catalog

The product API is mounted at `/api/product`. Product and category reads require
`products.view`; product edits, soft deletes and image changes require `products.manage`.
Product deletion is a soft delete and is refused while the stock module reports on-hand stock
for the product or one of its variants. The product module depends on the public `StockCheck`
interface only; `app/main.py` wires it to the stock module's implementation, so product never
imports stock internals.

Variants are managed under `/api/product/{product_id}/variants`. Reads require `products.view`;
creation, edits, and soft deletion require `products.manage`. Variant attributes are normalized
case-insensitively, validated against the effective category attribute definitions, and expose
variant-specific stock and effective price. Duplicate combinations and SKUs are field errors.
The stock interface returns a quantity map keyed by variant ID (with `null` for base stock), so
the product module can keep variant stock independent and block deletion when that variant has
stock. Variant and category-attribute changes are audited in the same transaction.

Reusable attribute definitions are managed at
`/api/product/categories/{category_id}/attributes`; definitions inherit through category
ancestors, with the nearest definition winning. Deleting a definition does not change existing
variants.

Categories are managed by the product module at `/api/product/categories`. The flat category
response is in tree order and includes ancestor paths, direct active-product counts, and
roll-up counts for all active products in descendants. The category product endpoint uses a
recursive PostgreSQL CTE, so arbitrary-depth hierarchies do not require per-level queries.
Creating, moving, and deleting categories take the same transaction-level advisory lock for
the category tree. Moves validate the complete descendant set while holding that lock, which
prevents concurrent opposing moves from creating a cycle. Sibling names are unique; unknown
parents, self/descendant moves, and duplicate siblings are field errors. A category cannot be
deleted while any child or product row references it, including inactive products. Category
changes record `category_created`, `category_updated`, `category_moved`, and
`category_deleted` in the same transaction as the data change. Product responses resolve the
category path by ID at read time, so renames are immediately reflected in listings and
dropdowns.

JPEG, PNG and WebP uploads are checked by magic bytes, assigned a random server-side filename,
and limited by `PRODUCT_IMAGE_MAX_BYTES` (5 MiB by default). Files are stored in the
`product-images` Docker volume and served only through authenticated API routes with
`X-Content-Type-Options: nosniff`. Soft deletion retains image records and files for history.

## User management

Admins manage accounts through `/api/auth/users` (paged list, detail, create, edit,
deactivate and reactivate), all guarded by `users.manage`. Creation stores an unusable
password hash, issues the existing single-use, time-limited password-reset token, and
emails only its setup link; the API never returns or audits a password or token. A
deactivation is retained rather than hard-deleted, revokes all sessions immediately, and
is recorded with the before/after active state. An Admin cannot disable or demote
themselves or the last active Admin. An Admin can unlock an account locked after failed
logins before the lockout expires (`POST /api/auth/users/{id}/unlock`, SRS A-12); listings
report `is_locked`, and the unlock is audited as `user_unlocked`.

Locations remain owned by `stock`. The stock module exposes `/api/stock/locations` (active
locations in the caller's scope) and a public service-level location validator; the
composition root wires that validator into auth. Auth therefore validates location IDs
without importing stock internals or touching stock tables. Admins and Managers manage
locations on the `/locations` screen (`locations.manage`), backed by
`GET /api/stock/locations/all` (inactive ones included) and the create/update routes, which
record `location_created` and `location_updated`.

## Stock items

`product.product_stock_items(db, product_ids=None)` lists, for every product, its base item
(`variant_id` null) and each of its variants, with `is_active` saying whether the item may take
new stock: an active variant of an active product, or the base item of an active product with no
active variants. Display paths (stock levels, POS availability, reports, PO and supplier
catalog lines) resolve labels for any item, so rows made before a product gained variants or
was deleted still show; empty rows of inactive items are left out of stock screens. New stock
(`update_stock` increases, transfers), reorder settings, PO lines and supplier catalog entries
require an active item. A variant cannot be added while the product has base stock, and
deleting a product or variant, or adding a product's first variant, resolves the now stale
low/out-of-stock alerts through `notifications.resolve_stock_alerts`. Reorder threshold changes
are audited as `reorder_settings_updated`; the Stock levels screen edits them per item and
location.
