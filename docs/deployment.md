# Deployment

ESIMS ships as containers, so the same steps work on any cloud VM or on a plain on-prem server
(NFR-13). The production stack is `docker-compose.prod.yml`:

| Service   | Image                          | Role                                                              |
| --------- | ------------------------------ | ----------------------------------------------------------------- |
| `db`      | `postgres:16-alpine`           | PostgreSQL, data in the `db-data` volume                          |
| `migrate` | `backend/Dockerfile.prod`      | Runs `alembic upgrade head`, then exits                           |
| `backend` | `backend/Dockerfile.prod`      | FastAPI behind uvicorn, non-root, starts after the migration      |
| `web`     | `frontend/Dockerfile.prod`     | Caddy: serves the built SPA, proxies `/api`, terminates HTTPS     |

Only `web` publishes ports (80 and 443). The database and API are reachable inside the Compose
network only.

## Requirements

A Linux host with Docker Engine and the Compose plugin, 2 GB RAM or more, and a DNS name that points
at the host (for a public certificate).

## Deploy

```bash
git clone <repository-url> esims && cd esims
cp .env.prod.example .env.prod
# edit .env.prod: SITE_ADDRESS, POSTGRES_PASSWORD, DATABASE_URL
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

Check `https://<SITE_ADDRESS>/api/health` returns `{"status": "ok"}`.

To create the first accounts, see the user-management documentation once it exists. The sample data
script (`python -m scripts.seed`) is for development only; do not run it in production.

### Update

```bash
git pull
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

Migrations run automatically on every start. Logs: `docker compose -f docker-compose.prod.yml logs -f`.

## Production settings

All configuration is environment variables in `.env.prod` (reference: `.env.prod.example`).

| Variable            | Notes                                                                                      |
| ------------------- | ------------------------------------------------------------------------------------------ |
| `SITE_ADDRESS`      | Public domain: Caddy obtains and renews a Let's Encrypt certificate. HTTP redirects to HTTPS. |
| `POSTGRES_PASSWORD` | Generate randomly. Required; the stack refuses to start without it.                        |
| `DATABASE_URL`      | `postgresql://user:password@db:5432/esims` for the bundled database.                       |
| `COOKIE_SECURE`     | Keep `true`: session cookies are sent over HTTPS only.                                     |
| `CORS_ORIGINS`      | Leave empty; the SPA and API share one origin.                                             |

Never commit `.env.prod` (it is git-ignored).

## Cloud target: a VM on any provider (AWS EC2, DigitalOcean, Azure VM, ...)

1. Create an Ubuntu 24.04 VM (2 vCPU, 2 GB RAM). Allow inbound TCP 22, 80 and 443 only.
2. Point a DNS `A` record for your domain at the VM's public IP.
3. Install Docker: `curl -fsSL https://get.docker.com | sh`.
4. Follow **Deploy** above with `SITE_ADDRESS=<your domain>`.

To use the provider's managed PostgreSQL instead of the `db` container, set `DATABASE_URL` to its
connection string with `?sslmode=require`, and remove the `db` service and the `depends_on: db`
entry of `migrate` from a copy of the compose file.

## On-premises server

1. Install a Linux distribution with Docker Engine and the Compose plugin.
2. Give the server a fixed address and an internal DNS name (for example `esims.store.local`).
3. Set `SITE_ADDRESS` to that name. Caddy issues a certificate from its own CA; export the root
   certificate from the `caddy-data` volume (`/data/caddy/pki/authorities/local/root.crt`) and install
   it on the client machines to remove browser warnings. Alternatively, put the store's own certificate
   in place by adding a `tls <cert> <key>` line to `frontend/Caddyfile`.
4. Follow **Deploy** above. Make sure Docker starts on boot (`systemctl enable docker`); the services
   use `restart: unless-stopped`.

## Continuous integration

`.github/workflows/ci.yml` runs on every pull request and on pushes to `main`: backend lint,
import-linter and tests; frontend lint, tests and build; and a build of the production images.

To make failing checks block merging, enable branch protection on `main` (GitHub: Settings >
Branches > Require status checks to pass: `backend`, `frontend`, `production-build`).

Backups and monitoring are covered separately (backup and monitoring issues).
