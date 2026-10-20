# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

ESIMS (Electronics Store Inventory Management System): a modular-monolith web app (FastAPI, React + TypeScript with Vite, PostgreSQL). Requirements are in `Documents/*.docx` (SRS, security requirements, test plan, use cases). SRS section 5 "Assumptions and Design Decisions" (A-1..A-12) holds business rules stated nowhere else. Work is tracked as GitHub issues on the project board "Electronics Store Inventory management System"; each issue lists its SRS requirement IDs and dependencies.

## Commands

Everything runs in Docker. Do not install anything on the host (no pip/npm). `README.md` has the run, test and lint commands; source is bind-mounted, so edits apply immediately. Extras not in the README:

```bash
docker compose run --rm --no-deps backend pytest tests/test_health.py::test_health_returns_ok   # single backend test
docker compose run --rm --no-deps frontend npm test -- src/App.test.tsx                         # single frontend test
docker compose run --rm --user $(id -u):$(id -g) backend alembic revision --autogenerate -m "<change>"   # new migration, owned by you
```

Tests using the `conn`/`migrated_engine`/`empty_db_url` fixtures (`tests/conftest.py`) need the `db` service, so omit `--no-deps` for them. They run on throwaway databases, never the dev one.

After changing `frontend/package.json`, regenerate the lockfile in a container (the image uses `npm ci`), then rebuild the image:
`docker run --rm --user $(id -u):$(id -g) -e HOME=/tmp -v $PWD/frontend:/app -w /app node:22-alpine npm install`

## Architecture

Rationale and module list: `docs/architecture.md`. The part that needs enforcing in code:

- Each module under `backend/app/modules/` exposes only `__init__.py` / `service.py` (a `Protocol`) to other modules; `_internal/` is private. Modules never touch another module's tables.
- Dependencies point downward only: `reporting` > `sales | purchasing` > `stock` > `product` > `notifications` > `auth` > `audit`. A lower module that must react to a higher one (e.g. stock raising low-stock alerts) goes through `notifications`.
- import-linter contracts in `backend/pyproject.toml` enforce this, and `tests/test_architecture.py` runs them in pytest. When adding a module or changing the order, update the `layers` contract, add a matching "Nothing outside X uses its internals" contract, and update `docs/architecture.md`.
- Tables live in the owning module's `_internal/models.py` on `app.db.Base`. Register new model files in `backend/migrations/models.py`. Cross-module foreign keys point downward only and use string targets (`ForeignKey("products.id")`). Upward references are plain ID columns, and no ORM relationships cross modules. Autogenerate omits triggers, functions, sequences and data, so write those by hand. `tests/test_migrations.py` fails if models and migrations drift. See `docs/schema.md`.
- Config is environment variables only (`backend/app/config.py`); `.env.example` is the reference. The Vite dev server proxies `/api` to the backend.

## Workflow

Work on a feature branch (`feature/<issue>-<slug>`) and open a PR that says `Closes #<issue>`.

### Project board status

Statuses: `Backlog`, `Ready`, `In progress`, `In review`, `Done`. Keep them current:
1. Before starting an issue, move it to `In progress`.
2. When the work is finished (PR opened), move it to `In review`.
3. Then promote dependents: for each `Backlog` issue, read its `Dependencies` section, and if all of them are `In review` or `Done`, move it to `Ready`. Do not start them unless asked.

The project is number 2, owned by the repository owner:

```bash
gh project item-list 2 --owner <repo-owner> --limit 100 --format json   # find an issue's item id
gh project item-edit --project-id PVT_kwHOAqltvc4BlKdt --id <item-id> \
  --field-id PVTSSF_lAHOAqltvc4BlKdtzhj4YLw --single-select-option-id <option-id>
```

Option ids: Backlog `f75ad846`, Ready `61e4505c`, In progress `47fc9ee4`, In review `df73e18b`, Done `98236657`.
