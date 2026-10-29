# Performance and load test results

Generated 2026-10-29 13:29 UTC by `python -m scripts.loadtest`.
Re-run it to refresh this file; the profile is described in [`performance.md`](performance.md).

## Dataset

- 10003 products (10000 catalogue SKUs plus 3 hot items), 5 locations, 50003 stock rows.
- 10 concurrent API clients, 100 requests per scenario, 2 uvicorn workers.
- Target: p95 under 2 s (NFR-1).

## Search, list, filter and sort

| Scenario | Requests | Median (ms) | p95 (ms) | Max (ms) | Errors |
|---|---|---|---|---|---|
| list (page 1, by name) | 100 | 38 | 139 | 182 | 0 |
| list (deep page) | 100 | 43 | 83 | 91 | 0 |
| sort by price | 100 | 32 | 57 | 63 | 0 |
| sort by stock | 100 | 316 | 571 | 638 | 0 |
| filter by category | 100 | 19 | 43 | 51 | 0 |
| filter by price range | 100 | 17 | 103 | 108 | 0 |
| filter by stock status | 100 | 415 | 660 | 790 | 0 |
| search | 100 | 29 | 61 | 70 | 0 |

## Concurrent sales

- 128 sale attempts by 8 cashiers in 7.6 s (16.8/s): 80 recorded, 48 rejected as out of stock, 0 other

## Reports and exports

| Report | Time (s) | Size (KiB) |
|---|---|---|
| valuation report (JSON) | 1.8 | 13094 |
| reorder report (JSON) | 1.3 | 2171 |
| valuation export (CSV) | 1.5 | 3675 |
| valuation export (PDF) | 33.5 | 4239 |
| reorder export (CSV) | 1.0 | 560 |
| reorder export (PDF) | 6.7 | 778 |

## Checks

- PASS: p95 latency, list (page 1, by name) (139 ms over 100 requests, 0 errors)
- PASS: p95 latency, list (deep page) (83 ms over 100 requests, 0 errors)
- PASS: p95 latency, sort by price (57 ms over 100 requests, 0 errors)
- PASS: p95 latency, sort by stock (571 ms over 100 requests, 0 errors)
- PASS: p95 latency, filter by category (43 ms over 100 requests, 0 errors)
- PASS: p95 latency, filter by price range (103 ms over 100 requests, 0 errors)
- PASS: p95 latency, filter by stock status (660 ms over 100 requests, 0 errors)
- PASS: p95 latency, search (61 ms over 100 requests, 0 errors)
- PASS: no errors or deadlocks in concurrent sales (0 unexpected)
- PASS: stock consistent for HOT-1 (started 40, sold 40, left 0)
- PASS: stock consistent for HOT-2 (started 40, sold 40, left 0)
- PASS: stock consistent for HOT-3 (started 40, sold 40, left 0)
- PASS: valuation report (JSON) (1.8 s, 13094 KiB, HTTP 200)
- PASS: reorder report (JSON) (1.3 s, 2171 KiB, HTTP 200)
- PASS: valuation export (CSV) (1.5 s, 3675 KiB, HTTP 200)
- PASS: valuation export (PDF) (33.5 s, 4239 KiB, HTTP 200)
- PASS: reorder export (CSV) (1.0 s, 560 KiB, HTTP 200)
- PASS: reorder export (PDF) (6.7 s, 778 KiB, HTTP 200)
