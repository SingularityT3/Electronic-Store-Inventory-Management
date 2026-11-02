# Performance and load test results

Generated 2026-11-02 08:50 UTC by `python -m scripts.loadtest`.
Re-run it to refresh this file; the profile is described in [`performance.md`](performance.md).

## Dataset

- 10003 products (10000 catalogue SKUs plus 3 hot items), 5 locations, 50003 stock rows.
- 10 concurrent API clients, 100 requests per scenario, 2 uvicorn workers.
- Target: p95 under 2 s (NFR-1).

## Search, list, filter and sort

| Scenario | Requests | Median (ms) | p95 (ms) | Max (ms) | Errors |
|---|---|---|---|---|---|
| list (page 1, by name) | 100 | 103 | 233 | 331 | 0 |
| list (deep page) | 100 | 109 | 157 | 186 | 0 |
| sort by price | 100 | 104 | 167 | 213 | 0 |
| sort by stock | 100 | 584 | 892 | 1064 | 0 |
| filter by category | 100 | 72 | 114 | 157 | 0 |
| filter by price range | 100 | 77 | 198 | 319 | 0 |
| filter by stock status | 100 | 701 | 979 | 1265 | 0 |
| search | 100 | 77 | 139 | 228 | 0 |

## Concurrent sales

- 128 sale attempts by 8 cashiers in 6.5 s (19.6/s): 80 recorded, 48 rejected as out of stock, 0 other

## Reports and exports

| Report | Time (s) | Size (KiB) |
|---|---|---|
| valuation report (JSON) | 2.3 | 13094 |
| reorder report (JSON) | 1.5 | 2404 |
| valuation export (CSV) | 1.8 | 3675 |
| valuation export (PDF) | 13.1 | 4221 |
| reorder export (CSV) | 1.3 | 560 |
| reorder export (PDF) | 3.4 | 767 |

## Checks

- PASS: p95 latency, list (page 1, by name) (233 ms over 100 requests, 0 errors)
- PASS: p95 latency, list (deep page) (157 ms over 100 requests, 0 errors)
- PASS: p95 latency, sort by price (167 ms over 100 requests, 0 errors)
- PASS: p95 latency, sort by stock (892 ms over 100 requests, 0 errors)
- PASS: p95 latency, filter by category (114 ms over 100 requests, 0 errors)
- PASS: p95 latency, filter by price range (198 ms over 100 requests, 0 errors)
- PASS: p95 latency, filter by stock status (979 ms over 100 requests, 0 errors)
- PASS: p95 latency, search (139 ms over 100 requests, 0 errors)
- PASS: no errors or deadlocks in concurrent sales (0 unexpected)
- PASS: stock consistent for HOT-1 (started 40, sold 40, left 0)
- PASS: stock consistent for HOT-2 (started 40, sold 40, left 0)
- PASS: stock consistent for HOT-3 (started 40, sold 40, left 0)
- PASS: valuation report (JSON) (2.3 s, 13094 KiB, HTTP 200)
- PASS: reorder report (JSON) (1.5 s, 2404 KiB, HTTP 200)
- PASS: valuation export (CSV) (1.8 s, 3675 KiB, HTTP 200)
- PASS: valuation export (PDF) (13.1 s, 4221 KiB, HTTP 200)
- PASS: reorder export (CSV) (1.3 s, 560 KiB, HTTP 200)
- PASS: reorder export (PDF) (3.4 s, 767 KiB, HTTP 200)
