# Sales and invoice retention

ESIMS retains sales, returns, and invoices for at least eight calendar years from the date each record was created for its transaction: `sales.sold_at`, `returns.created_at`, or `invoices.issued_at`. The eight-year minimum follows SRS A-2. The store owner must confirm the applicable local tax and GST rules before go-live. `RETENTION_YEARS` can raise the period but cannot be set below eight.

The database blocks early row deletion and all truncation for sales, returns, invoices, and their detail/link rows. Date fields used to start the clock are immutable. The database floor is eight years; when configuration is higher, the operator tool uses the configured period. There is no application delete route. Users are deactivated, products are soft-deleted, and locations referenced by sales are restricted. Audit history remains append-only forever; stock movements and product history are outside this policy.

Run the operator report and a dry run before archiving. Take and verify a full backup first. Archive files are compressed JSON Lines with adjacent SHA256 files in `/retention-archive`; each line records its source table and row. Search an archive by its sale ID, then inspect its row objects.

```sh
docker compose run --rm backend python -m scripts.retention report
docker compose run --rm backend python -m scripts.retention archive
docker compose run --rm backend python -m scripts.retention archive --execute --limit 500
docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm backend python -m scripts.retention report
docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm backend python -m scripts.retention archive --execute
```

Backups use full-database `pg_dump`, so each includes all sales, returns, and invoices. Keep monthly backups for at least `RETENTION_YEARS x 12` months and store them off-server. Restore replaces schema and data; migrations restore retention triggers. A database owner or superuser can disable triggers, so use a restricted application database role and keep verified off-server backups.
