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
A route that needs the user takes `user: Annotated[CurrentUser, Depends(current_user)]`.
Role checks are #6.

Modules write audit entries with `audit_service.record(db, ...)` from `app.modules.audit`, in
the same transaction as the change they describe.

## Configuration

All settings come from environment variables (`backend/app/config.py`), with `ENV` selecting
`dev`, `test` or `prod`. `.env.example` lists the variables; the real `.env` is git-ignored.

## Frontend

`frontend/src/modules/` mirrors the backend modules. In development, Vite proxies `/api` to the
backend.

## Out of scope for the skeleton

UI shell (#4).
