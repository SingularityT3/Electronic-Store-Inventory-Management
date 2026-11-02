# Admin and setup guide

For the person who installs and runs ESIMS: installation, configuration, first accounts, backups,
monitoring and routine operations. Day-to-day use of the app is in [admin.md](admin.md) and the
other role guides. Commands below run from the repository folder on the server.

Shorthand used on this page:

```bash
alias esims='docker compose -f docker-compose.prod.yml --env-file .env.prod'
```

## 1. Install

You need a Linux server with Docker Engine and the Compose plugin, 2 vCPU and 2 GB RAM or more,
and a DNS name pointing at it. Step-by-step instructions for a cloud VM and an on-premises server,
and what each container does, are in [`../deployment.md`](../deployment.md). In short:

```bash
git clone https://github.com/SingularityT3/Electronic-Store-Inventory-Management.git esims
cd esims
cp .env.prod.example .env.prod
```

Edit `.env.prod` (next section), then:

```bash
esims up -d --build
esims ps
```

All services should be `Up` and `backend` `healthy` after a minute. Open
`https://<SITE_ADDRESS>/api/health`: it must show `{"status":"ok",...}`. Plain `http://`
redirects to HTTPS. Database migrations run automatically every time the stack starts.

## 2. Configure

Every setting is an environment variable in `.env.prod`; `.env.prod.example` documents each one
and [`../deployment.md`](../deployment.md#production-settings) has the full table. Never commit
`.env.prod`; keep a copy in your password manager.

| Setting | What to put |
| --- | --- |
| `SITE_ADDRESS` | The domain users type, e.g. `esims.mystore.in`. A public name gets a Let's Encrypt certificate; an internal name gets one from Caddy's own CA (see deployment.md for installing its root on store PCs). |
| `POSTGRES_PASSWORD`, `DATABASE_URL` | A random password (`openssl rand -hex 24`) and the matching URL `postgresql://esims:<password>@db:5432/esims`. |
| `STORE_NAME`, `STORE_GSTIN` | Printed on every invoice and credit note. |
| `GST_RATE` | Default 18 (%). |
| `SMTP_*` | Your mail server, so users get invite and password reset links. Strongly recommended; see section 4 if you have none. |
| `MONITOR_*` | Store hours and where outage alerts go (email and/or a Slack/Discord webhook). |
| `BACKUP_PATH` | A folder on storage that is **not** this server (NAS, mounted share, external disk). |
| `RETURN_WINDOW_DAYS`, `LOCKOUT_*`, `SESSION_*`, `RETENTION_YEARS` | Business rules; the defaults follow the SRS (30 days; 5 tries / 15 minutes; 30 minutes idle / 12 hours; 8 years). |

After changing `.env.prod`, apply it with `esims up -d`.

## 3. First Admin, locations and users

1. Create the first Admin (you are asked for the password twice; it is never shown):

   ```bash
   esims run --rm backend python -m scripts.create_admin owner "Store Owner" --email owner@mystore.in
   ```

2. Sign in at `https://<SITE_ADDRESS>` as that Admin.
3. **Inventory > Locations > New location**: add each store and warehouse.
4. **Administration > User management > Add user**: add the Managers, Staff and Cashiers. Staff
   and Cashiers need a **Location**. Each user gets an email with a link to set their password.
   See [admin.md](admin.md#user-accounts-and-roles-uc-02) for roles.
5. A Manager then loads the catalog: categories, products, suppliers and their catalogs, reorder
   thresholds, and receives the opening stock on purchase orders (see [manager.md](manager.md)).

Do **not** run `scripts.seed` in production; it loads sample data with a shared password.

## 4. Users and passwords without email

If `SMTP_HOST` is empty, no invite or reset email is sent. Set a password on the server and give
it to the user in person:

```bash
esims run --rm backend python -m scripts.set_password <username>
```

It ends the user's open sessions, clears a lockout and is written to the audit log. Ask users to
pick their own password with **Forgot password?** once email is set up. Create additional Admins
with `scripts.create_admin` or in User management.

## 5. Backups and restore

The `backup` container makes a full backup every day at `BACKUP_TIME` (02:00) into
`BACKUP_PATH`: the database (`db.dump`), product images (`images.tar.gz`) and checksums. It keeps
every backup for 30 days and one per month for 96 months (8 years, matching record retention).
A failed or overdue backup sends an alert through the monitoring channels.

```bash
esims exec backup python3 -m scripts.backup run      # back up now (do this before upgrades)
esims exec backup python3 -m scripts.backup check    # is the newest backup under 26 hours old?
ls <BACKUP_PATH>                                     # one folder per backup, named by UTC time
```

To restore (replaces all current data):

```bash
esims stop web backend monitor
esims run --rm backup python3 -m scripts.backup restore <folder name, e.g. 20261026T020000Z>
esims up -d
```

Then check health, sign in, open a recent sale and a product image. The full recovery plan, how to
restore onto a new server, recovery time and point, and the restore drill log are in
[`../backup-recovery.md`](../backup-recovery.md). Repeat the drill once a year.

## 6. Monitoring

The `monitor` container checks `/api/health` every 30 seconds and sends one "DOWN" alert after
two failures and a "Recovered" alert afterwards, to `MONITOR_ALERT_TO` and/or
`MONITOR_WEBHOOK_URL`.

```bash
esims run --rm monitor python -m scripts.uptime alert "Test alert"           # test your channels
esims exec monitor python -m scripts.uptime report 2026-11-01 2026-11-30    # uptime % in store hours
esims logs -f backend                                                        # request and error log
```

The monitor runs on the same server, so it cannot report the whole server going down: also point
an external checker (UptimeRobot, Better Stack, ...) at `https://<SITE_ADDRESS>/api/health`.
Details: [`../monitoring.md`](../monitoring.md).

## 7. Record retention

Sales, returns and invoices cannot be deleted for 8 years (`RETENTION_YEARS`, SRS A-2; confirm
your GST obligations). After that an operator can archive expired records:

```bash
esims run --rm backend python -m scripts.retention report
esims run --rm backend python -m scripts.retention archive            # dry run
esims run --rm backend python -m scripts.retention archive --execute  # after a verified backup
```

See [`../retention.md`](../retention.md).

## 8. Updating

```bash
esims exec backup python3 -m scripts.backup run
git pull
esims up -d --build
```

Migrations run on start. Check `esims ps` and the health URL afterwards.

## 9. Troubleshooting

| Symptom | Check |
| --- | --- |
| Browser certificate warning | `SITE_ADDRESS` must match the address typed; for an internal name, install Caddy's root certificate on the PCs (deployment.md). |
| Health shows `unhealthy` / 503 | The database is down: `esims ps`, `esims logs db`. |
| Users get no invite or reset email | `SMTP_*` settings; `esims logs backend` shows "Could not send password reset email". Use `scripts.set_password` meanwhile. |
| Someone is locked out | User management > **Unlock**, or wait 15 minutes. |
| Invoices show the wrong store name or GSTIN | `STORE_NAME` / `STORE_GSTIN` in `.env.prod`, then `esims up -d`. Invoices already issued keep what they were issued with. |
| `docker compose ps` shows `backup` unhealthy | No backup in 26 hours: `esims logs backup`, check `BACKUP_PATH` is mounted and has space. |
