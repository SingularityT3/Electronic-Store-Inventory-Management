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

## Test and lint

```bash
docker compose run --rm --no-deps backend pytest
docker compose run --rm --no-deps backend ruff check .
docker compose run --rm --no-deps backend ruff format --check .
docker compose run --rm --no-deps backend lint-imports
docker compose run --rm --no-deps frontend npm test
docker compose run --rm --no-deps frontend npm run lint
docker compose run --rm --no-deps frontend npm run build
```

`ruff format .` and `npm run format` apply formatting.

## Layout

```
backend/    FastAPI app (app/modules/<module>/ ...), tests/, pyproject.toml
frontend/   React app (src/modules/ mirrors the backend modules)
docs/       Architecture notes
Documents/  SRS, security requirements, test plan, use cases
```

## Configuration

Settings are environment variables; see `.env.example`. `.env` is git-ignored. Do not commit
secrets.
