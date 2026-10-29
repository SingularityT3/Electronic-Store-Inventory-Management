# Performance and load testing

Verifies NFR-1 (search, list, filter and sort under 2 s), NFR-2 (concurrent counters) and NFR-3
(growth in SKUs and locations). The latest numbers are in
[`performance-results.md`](performance-results.md).

## Run it

```bash
docker compose run --rm backend python -m scripts.loadtest --output /app/loadtest-results.md
```

The script needs only the compose `db` service. It creates a throwaway database, migrates it,
seeds it with SQL, starts the API on a free port with 2 uvicorn workers, runs the scenarios over
HTTP and drops the database. It exits non-zero if a target is missed. Options (`--skus`,
`--locations`, `--concurrency`, `--requests`, `--cashiers`, `--threshold`, ...) are listed by
`--help`. To refresh the committed results, copy `backend/loadtest-results.md` over
`docs/performance-results.md` after a run. The `Load test` workflow runs it nightly and on demand.

## Load profile

| Item | Default |
|---|---|
| Catalogue | 10,000 SKUs in 40 categories, plus 3 "hot" items for the sale test |
| Locations | 5 (one warehouse, four stores), a stock row per SKU and location (50,000 rows) |
| Alerts | One low or out-of-stock alert per stock row at or below its threshold |
| Read load | 10 concurrent clients, 100 requests per scenario |
| Scenarios | list (first and deep page), sort by price, sort by stock, filter by category, price range and stock status, search |
| Sales | 8 cashiers at one store, 16 sale attempts each. Even cashiers sell hot item 1 then 2, odd cashiers 2 then 1 (opposite lock order); every other attempt sells hot item 3 alone. Each hot item has 40 units, so the attempts exceed stock |
| Reports | Valuation (50,003 rows) and reorder reports, as JSON, CSV and PDF |

## Pass criteria

- p95 latency under 2 s for every read scenario, with no errors (NFR-1).
- No response other than 201 (sold) or 409 (out of stock) during the sale test, so no 5xx,
  timeouts or deadlocks; each hot item ends with `initial - units sold` on hand, never below
  zero (NFR-2).
- Every report and export returns 200 within 60 s.

## Hotspots found and fixed

Sorting by stock and filtering by stock status took about 2.2 s at p95. Both need stock for
every match, and the handler loaded a full row (category path, variant count) for all 10,000
products, looked stock up with a 10,000-parameter `IN` list and read every active alert as an
ORM object. It now:

- reads only product ids for the sort or filter, then loads full rows for the one page shown;
- passes the ids to the stock lookup as a single array parameter;
- reads only the alerted product ids (`alerted_product_ids`) instead of whole alerts.

Both scenarios are now around 0.6 s at p95.

## Known limits

- The PDF of the 50,000-row valuation report takes about 33 s, since the PDF library draws
  roughly 1,500 rows per second. A 5,000-row PDF takes about 3 s and the per-location reports
  stay under 10 s. CSV export of the full report takes about 1.5 s. If full-store PDFs matter,
  filter by location or export CSV.
- The test runs against a local Postgres in Docker, so absolute times depend on the host. CI
  numbers are lower-bound checks of the 2 s target, not capacity planning.
