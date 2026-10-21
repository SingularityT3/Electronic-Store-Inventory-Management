# Architecture

ESIMS is a modular monolith: one FastAPI backend, one React (Vite, TypeScript) frontend, one
PostgreSQL database. It follows the component diagram in `Documents/esims_component_diagram.png`
and SRS NFR-11 (separate product, stock, sales and reporting concerns).

## Modules (`backend/app/modules/`)

| Module          | Responsibility                                                          |
| --------------- | ----------------------------------------------------------------------- |
| `product`       | Catalog, hierarchical categories, variants, search/filter               |
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

The menu is built from `NAV_ITEMS` in `shell/navigation.ts`: each item names the permission it
needs, and the sidebar shows an item only if the server-sent `permissions` of the signed-in user
include it, so each role sees exactly its screens (FR5.1-IT-3). Menu hiding is cosmetic. Every
item's route, and any sub-route under it, is also wrapped in `RequirePermission`, which shows the
access-denied page for a URL typed by hand; the API enforces the same rule with a 403 (NFR-7).

To add a screen, give its feature module a page component and replace the `PlaceholderPage` for
its path in `App.tsx`. A new menu item is one entry in `NAV_ITEMS`.
