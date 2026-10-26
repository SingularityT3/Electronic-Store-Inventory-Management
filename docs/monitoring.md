# Monitoring and uptime (NFR-4)

Target: 99.5% availability during store hours.

## What is monitored

- **Health endpoint** `GET /api/health`: runs `SELECT 1` against the database. Returns `200
  {"status":"ok","checks":{"database":"ok"}}`, or `503 {"status":"unhealthy",...}` when the database
  is unreachable. Public, no data exposed. Docker's health check for `backend` uses it too.
- **Request log**: every request is logged as `METHOD /path -> status in N ms`; 5xx responses and
  unhandled exceptions are logged at ERROR with a stack trace. Read with
  `docker compose -f docker-compose.prod.yml logs -f backend`.
- **Uptime monitor**: the `monitor` service (`backend/scripts/uptime.py`) polls the health endpoint
  every 30 s (`MONITOR_INTERVAL_SECONDS`) and appends each result to `/data/uptime/checks.jsonl`
  (volume `uptime-data`).

## Alerts

After 2 consecutive failed polls (`MONITOR_FAILURES_BEFORE_ALERT`) the monitor sends one "DOWN"
alert, and one "Recovered" alert when the check passes again. So an outage is reported within about
a minute. Channels, either or both:

- email: set `MONITOR_ALERT_TO` (uses the `SMTP_*` settings);
- chat: set `MONITOR_WEBHOOK_URL` (Slack or Discord incoming webhook).

For outages of the whole server, which the monitor cannot see from inside, also point an external
service (UptimeRobot, Better Stack, Uptime Kuma on another host) at `https://<SITE_ADDRESS>/api/health`
with email/chat alerts, or run the `monitor` container on a different host with `MONITOR_HEALTH_URL`
set to the public URL.

### Backup failures (#36)

The backup job should call this when it fails:

```bash
docker compose -f docker-compose.prod.yml run --rm monitor python -m scripts.uptime alert "Database backup failed"
```

## Reporting uptime

Uptime = successful polls / all polls made during store hours (`MONITOR_STORE_HOURS`, local to
`MONITOR_TIMEZONE`, on the days in `MONITOR_STORE_DAYS`). Polls outside store hours are ignored, so
night-time maintenance does not count against the 99.5% target. Dates are inclusive:

```bash
docker compose -f docker-compose.prod.yml exec monitor python -m scripts.uptime report 2026-03-01 2026-03-31
# {"from": "2026-03-01", "to": "2026-03-31", "checks": 20160, "successful": 20102, "uptime_percent": 99.712}
```

`uptime_percent` is `null` if there were no polls in the period. The figure is sample-based, so its
resolution is the poll interval. Planned maintenance is not excluded; note it in the monthly report.

## Simulating an outage

```bash
docker compose -f docker-compose.prod.yml stop db      # health goes 503 -> alert in ~1 minute
docker compose -f docker-compose.prod.yml start db     # "Recovered" alert
```
