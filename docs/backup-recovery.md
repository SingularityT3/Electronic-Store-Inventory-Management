# Backups and recovery plan (NFR-5)

## What is backed up

The `backup` service (`backend/scripts/backup.py`, image `backend/Dockerfile.backup`) runs every day
at `BACKUP_TIME` (default 02:00, in `MONITOR_TIMEZONE`). Each run writes a directory
`<BACKUP_PATH>/<UTC timestamp>/`:

| File            | Content                                                                 |
| --------------- | ----------------------------------------------------------------------- |
| `db.dump`       | the whole PostgreSQL database (`pg_dump` custom format), including audit log, sales and invoices |
| `images.tar.gz` | the product image directory (`product-images` volume)                    |
| `SHA256SUMS`    | checksums, verified before any restore                                  |

A backup is built in a temporary directory, the dump is test-read with `pg_restore --list`, and only
then is the directory renamed into place, so every listed backup is complete. Passwords and `.env.prod`
are not part of a backup; keep `.env.prod` in your password manager or offline copy.

## Where backups go

Set `BACKUP_PATH` in `.env.prod` to a directory on **storage that is not the app server**: a mounted
NFS/SMB share, a NAS, or a cloud disk or bucket mounted with a FUSE tool. Example for a NAS mounted at
`/mnt/esims-backups`: `BACKUP_PATH=/mnt/esims-backups`. If `BACKUP_PATH` is empty, backups go to the
Docker volume `backups` on the same host, which protects against data corruption and mistakes but not
against losing the server or its disk. Do not leave it that way in production.

## Retention

- every backup from the last **30 days** (`BACKUP_KEEP_DAILY_DAYS`);
- then the first backup of each month for at least `RETENTION_YEARS x 12` months. The default is
  **96 months** (`BACKUP_KEEP_MONTHLY`), matching the eight-year minimum in SRS A-2, #27. The backup
  check rejects a lower configured value.

Older backups are deleted after each successful run; the newest backup is never deleted. At about
tens of MB per dump this stays small; check free space on the backup storage yearly.

## Failure alerts

- A run that fails (database unreachable, disk full, unreadable dump) sends `[ESIMS] Database backup
  failed` with the error to the channels of the uptime monitor (`MONITOR_ALERT_TO`,
  `MONITOR_WEBHOOK_URL`; see [`monitoring.md`](monitoring.md)) and leaves no partial backup.
- After each run the job also checks that the newest backup is under 26 hours old, and sends
  `[ESIMS] Backup is overdue` if not.
- The container's Docker health check runs the same age check hourly; `docker compose ps` shows
  `unhealthy` if backups stop. A stopped container cannot alert, so look at the backup storage
  (newest directory name = last backup time) when you check the monitoring weekly.

Run one on demand, or check, with:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod exec backup python3 -m scripts.backup run
docker compose -f docker-compose.prod.yml --env-file .env.prod exec backup python3 -m scripts.backup check
```

## Recovery plan

**Who:** the system administrator (the person holding the server and `.env.prod`); the store manager
decides when to restore and confirms the data afterwards.
**Recovery point:** up to 24 hours of data (back to the last 02:00 backup). Sales and stock movements
after that must be re-entered from paper or receipts. Run an extra backup (`run`, above) before any
planned risky change to shrink this.
**Recovery time:** about 1 hour for a restore on the same server, 2 to 4 hours if a new server must be
built first (drill below: the restore itself takes seconds for a small database; the rest is setup).

### Restore on the existing server

1. Find the backup: `ls <BACKUP_PATH>`. Pick the newest unless told otherwise.
2. Stop the application so nothing writes during the restore:
   `docker compose -f docker-compose.prod.yml --env-file .env.prod stop web backend monitor`
3. Restore (replaces all current data in the database with the backup's, and unpacks the images):

   ```bash
   docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm backup \
     python3 -m scripts.backup restore 20261026T020000Z
   ```

   It verifies the checksums first and restores in one transaction: if anything fails, the database
   is unchanged. Files in the image volume that are not in the backup are left alone. Retention
   triggers are part of the schema and return with the restored schema and migrations.
4. Start everything: `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d`
   (migrations run on start and bring an older backup up to the current schema).
5. Verify: `https://<SITE_ADDRESS>/api/health` is `ok`; log in; open Products and a recent sale or
   purchase order; confirm product images load. Tell the manager which backup time was restored.

### Restore on a new server (server or disk lost)

1. Provision the host and install Docker as in [`deployment.md`](deployment.md); clone the repository;
   put `.env.prod` back (same `POSTGRES_*` and `DATABASE_URL`).
2. Mount the backup storage at the same `BACKUP_PATH`.
3. Start only the database: `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d db`
4. Run step 3 above (the restore into the empty database), then `up -d --build` to start the rest.
5. Point DNS at the new host if its address changed, then do step 5 above.

### Restore by hand (if the `backup` image is unavailable)

```bash
sha256sum -c SHA256SUMS
pg_restore --clean --if-exists --no-owner --single-transaction -d esims db.dump
tar -xzf images.tar.gz -C /data      # creates /data/product-images
```

## Restore drill

Done on 2026-10-26 on an empty environment (fresh database, empty image volume), with the development
Compose stack's PostgreSQL 16 and the real `backup` image:

1. Migrated a database to the current schema and loaded the sample data (12 products, 4 users); put
   a file in the image volume.
2. `scripts.backup run`: produced `db.dump`, `images.tar.gz` and `SHA256SUMS`.
3. Created a second, empty database and an empty image volume; ran `scripts.backup restore <stamp>`.
4. Result: 12 products, 4 users, migration version `0007`, and the image file identical. `check`
   reported the backup as current. A run against an unreachable database failed with exit code 1,
   logged the alert, and left no partial backup.

Repeat the drill (on a copy, never on the live database) after any change to the backup job, after
major upgrades, and at least once a year. Record the date and result here.

| Date       | Environment            | Result |
| ---------- | ---------------------- | ------ |
| 2026-10-26 | clean Docker, PG 16    | data and images recovered intact |
