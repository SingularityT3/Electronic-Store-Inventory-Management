# Electronics Store Inventory Management System (ESIMS)

Web application for managing products, stock, purchasing, sales and reports for electronics
stores. Requirements are in `Documents/`; the module layout is in
[`docs/architecture.md`](docs/architecture.md).

Stack: FastAPI (Python 3.12), React + TypeScript (Vite), PostgreSQL 16. Everything runs in Docker,
so the only prerequisite is Docker with the Compose plugin. Nothing is installed locally.

## Run

```bash
cp .env.example .env
docker compose up --build
```

- Frontend: http://localhost:5173
- API health check: http://localhost:8000/api/health
- API docs: http://localhost:8000/docs
- Mailpit (catches outgoing email, e.g. password reset links): http://localhost:8025

## Database

Create the schema, then optionally load sample data (locations, categories, products, stock,
suppliers, and the users `admin`, `manager`, `staff` and `cashier`, whose password is
`SEED_USER_PASSWORD` from `.env`):

```bash
docker compose run --rm backend alembic upgrade head
docker compose run --rm backend python -m scripts.seed
```

The schema and the rules it enforces are in [`docs/schema.md`](docs/schema.md).
Record retention and the operator archive procedure are in [`docs/retention.md`](docs/retention.md).

## Test and lint

Backend tests need the database (they create and drop their own throwaway databases), so that
command starts `db`:

```bash
docker compose run --rm backend pytest
docker compose run --rm --no-deps backend ruff check .
docker compose run --rm --no-deps backend ruff format --check .
docker compose run --rm --no-deps backend lint-imports
docker compose run --rm --no-deps frontend npm test
docker compose run --rm --no-deps frontend npm run lint
docker compose run --rm --no-deps frontend npm run build
```

`ruff format .` and `npm run format` apply formatting.

Every case in the test plan is mapped to its tests in
[`backend/tests/TRACEABILITY.md`](backend/tests/TRACEABILITY.md); `tests/test_traceability.py` keeps
that table in step with the plan and the test code.

Performance and load test (10,000 SKUs, concurrent sales, large exports):
[`docs/performance.md`](docs/performance.md).

## Deploy

Production images, HTTPS and cloud / on-premises steps: [`docs/deployment.md`](docs/deployment.md).
CI runs lint, tests and builds on every pull request.

## Layout

```
backend/    FastAPI app (app/modules/<module>/ ...), migrations/, scripts/seed.py, tests/
frontend/   React app (src/modules/ mirrors the backend modules)
docs/       Architecture, schema and deployment notes
Documents/  SRS, security requirements, test plan, use cases
```

## Configuration

Settings are environment variables; see `.env.example`. `.env` is git-ignored. Do not commit
secrets.
