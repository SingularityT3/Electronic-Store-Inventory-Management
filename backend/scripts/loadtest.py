"""Performance and load test (NFR-1, NFR-2, NFR-3).

Builds a throwaway database with a large catalogue, starts the API against it and measures:

1. search, list, filter and sort latency (p95 must stay under the target, NFR-1);
2. concurrent cashiers selling the same items: no errors, deadlocks or overselling (NFR-2);
3. reports and CSV/PDF exports over thousands of rows.

Run it with `docker compose run --rm backend python -m scripts.loadtest`; the exit status is
non-zero when a target is missed, so CI or a nightly job can run it unchanged. Nothing touches
the development database. See docs/performance.md for the profile and the latest results.
"""

import argparse
import socket
import statistics
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text

from app.db import database_url
from app.modules.auth._internal.passwords import hash_password

BACKEND_DIR = Path(__file__).resolve().parent.parent
PASSWORD = "load-test-password"
CSRF_COOKIE, CSRF_HEADER = "esims_csrf", "X-CSRF-Token"
UNIT_PRICE = "100.00"
SALE_TOTAL = "118.00"  # UNIT_PRICE plus the default 18% GST

BRANDS = ["Samsung", "Apple", "Sony", "Dell", "Lenovo", "Boat", "JBL", "Anker", "Xiaomi", "HP"]
SEARCH_TERMS = ["Galaxy", "load item 77", "LT-00", "Sony", "Accessories", "zzz-no-match"]


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


@dataclass
class Results:
    latency: list[tuple[str, int, float, float, float, float]] = field(default_factory=list)
    reports: list[tuple[str, float, int]] = field(default_factory=list)
    sales: list[str] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)

    def check(self, name: str, passed: bool, detail: str) -> None:
        self.checks.append(Check(name, passed, detail))
        print(f"[{'PASS' if passed else 'FAIL'}] {name}: {detail}", flush=True)


def percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(pct / 100 * (len(ordered) - 1))))]


def migrate_and_seed(engine: Engine, url, skus: int, locations: int, cashiers: int) -> None:
    config = Config(BACKEND_DIR / "alembic.ini")
    config.set_main_option(
        "sqlalchemy.url", url.render_as_string(hide_password=False).replace("%", "%%")
    )
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")

    password_hash = hash_password(PASSWORD)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO locations (name, type) "
                "SELECT 'LT Location ' || n, CASE WHEN n = 1 THEN 'warehouse' ELSE 'store' END "
                "FROM generate_series(1, :n) AS n"
            ),
            {"n": locations},
        )
        conn.execute(
            text(
                "INSERT INTO categories (name, parent_id) "
                "SELECT 'LT Category ' || n, NULL FROM generate_series(1, 10) AS n"
            )
        )
        conn.execute(
            text(
                "INSERT INTO categories (name, parent_id) "
                "SELECT 'LT Sub ' || n, c.id FROM generate_series(1, 30) AS n "
                "JOIN categories c ON c.name = 'LT Category ' || (1 + n % 10)"
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO products (sku, name, category_id, brand, price)
                SELECT 'LT-' || lpad(n::text, 6, '0'),
                       'Load Item ' || n || ' ' || (CAST(:brands AS text[]))[1 + n % :brand_count],
                       (SELECT id FROM categories WHERE name = 'LT Sub ' || (1 + n % 30)),
                       (CAST(:brands AS text[]))[1 + n % :brand_count],
                       (50 + (n * 37) % 90000)::numeric(12, 2)
                FROM generate_series(1, :n) AS n
                """
            ),
            {"n": skus, "brands": BRANDS, "brand_count": len(BRANDS)},
        )
        conn.execute(
            text(
                """
                INSERT INTO stock_levels (product_id, location_id, quantity, reorder_threshold)
                SELECT p.id, l.id, ((p.id * 7 + l.id * 13) % 60), 10
                FROM products p CROSS JOIN locations l WHERE p.sku LIKE 'LT-%'
                """
            )
        )
        # Seeded rows bypass update_stock, so raise the low-stock alerts it would have raised.
        conn.execute(
            text(
                """
                INSERT INTO stock_alerts (product_id, location_id, product_name, sku,
                                          location_name, alert_type, quantity, threshold)
                SELECT s.product_id, s.location_id, p.name, p.sku, l.name,
                       CASE WHEN s.quantity = 0 THEN 'out_of_stock' ELSE 'low_stock' END,
                       s.quantity, s.reorder_threshold
                FROM stock_levels s
                JOIN products p ON p.id = s.product_id
                JOIN locations l ON l.id = s.location_id
                WHERE s.quantity <= s.reorder_threshold
                """
            )
        )
        conn.execute(
            text(
                "INSERT INTO item_costs (product_id, average_cost) "
                "SELECT id, price * 0.7 FROM products WHERE sku LIKE 'LT-%'"
            )
        )
        # Hot items for the concurrency test, all stocked at the first store location.
        conn.execute(
            text(
                "INSERT INTO products (sku, name, category_id, brand, price) "
                "SELECT 'HOT-' || n, 'Hot Item ' || n, (SELECT min(id) FROM categories), "
                "'Hot', :price FROM generate_series(1, 3) AS n"
            ),
            {"price": UNIT_PRICE},
        )
        conn.execute(
            text(
                "INSERT INTO stock_levels (product_id, location_id, quantity) "
                "SELECT p.id, (SELECT id FROM locations WHERE name = 'LT Location 2'), 40 "
                "FROM products p WHERE p.sku LIKE 'HOT-%'"
            )
        )
        conn.execute(
            text(
                "INSERT INTO users (username, full_name, password_hash, role, location_id) "
                "VALUES ('lt_manager', 'Load Manager', :hash, 'manager', NULL)"
            ),
            {"hash": password_hash},
        )
        conn.execute(
            text(
                "INSERT INTO users (username, full_name, password_hash, role, location_id) "
                "SELECT 'lt_cashier_' || n, 'Load Cashier ' || n, :hash, 'cashier', "
                "(SELECT id FROM locations WHERE name = 'LT Location 2') "
                "FROM generate_series(1, :n) AS n"
            ),
            {"hash": password_hash, "n": cashiers},
        )
        conn.execute(text("ANALYZE"))


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start_api(url, port: int, workers: int) -> subprocess.Popen:
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "DATABASE_URL": url.render_as_string(hide_password=False),
        "COOKIE_SECURE": "false",
        "ENV": "test",
    }
    process = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
            "--port", str(port), "--workers", str(workers), "--log-level", "warning",
        ],
        cwd=BACKEND_DIR,
        env=env,
    )  # fmt: skip
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=2).status_code == 200:
                return process
        except httpx.HTTPError:
            time.sleep(0.5)
    process.terminate()
    raise RuntimeError("API did not start")


def session(base: str, username: str) -> httpx.Client:
    client = httpx.Client(base_url=base, timeout=60)
    response = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    response.raise_for_status()
    client.headers[CSRF_HEADER] = client.cookies.get(CSRF_COOKIE) or ""
    return client


def measure(client: httpx.Client, path: str) -> tuple[float, int]:
    start = time.perf_counter()
    response = client.get(path)
    return time.perf_counter() - start, response.status_code


def latency_phase(base: str, results: Results, args: argparse.Namespace) -> None:
    clients = [session(base, "lt_manager") for _ in range(args.concurrency)]
    paths = {
        "list (page 1, by name)": "/api/product?page=1&page_size=50",
        "list (deep page)": f"/api/product?page={args.skus // 100}&page_size=50",
        "sort by price": "/api/product?sort=price&order=desc&page_size=50",
        "sort by stock": "/api/product?sort=stock&order=desc&page_size=50",
        "filter by category": "/api/product?category_id={category}&page_size=50",
        "filter by price range": "/api/product?min_price=500&max_price=5000&page_size=50",
        "filter by stock status": "/api/product?stock_status=low_stock&page_size=50",
        "search": "/api/product?q={term}&page_size=50",
    }
    category = clients[0].get("/api/product/categories").json()[0]["id"]
    for label, template in paths.items():
        queue = [
            template.format(category=category, term=SEARCH_TERMS[i % len(SEARCH_TERMS)])
            for i in range(args.requests)
        ]

        def run(job: tuple[int, str]) -> tuple[float, int]:
            index, path = job
            return measure(clients[index % len(clients)], path)

        with ThreadPoolExecutor(args.concurrency) as pool:
            samples = list(pool.map(run, enumerate(queue)))
        times = [seconds for seconds, _ in samples]
        errors = sum(1 for _, code in samples if code != 200)
        p95 = percentile(times, 95)
        results.latency.append(
            (label, len(samples), statistics.median(times), p95, max(times), errors)
        )
        results.check(
            f"p95 latency, {label}",
            p95 < args.threshold and errors == 0,
            f"{p95 * 1000:.0f} ms over {len(samples)} requests, {errors} errors",
        )
    for client in clients:
        client.close()


def sell(client: httpx.Client, product_ids: list[int], location_id: int) -> int:
    response = client.post(
        "/api/sales",
        json={
            "location_id": location_id,
            "lines": [{"product_id": pid, "quantity": 1} for pid in product_ids],
            "payments": [
                {"method": "cash", "amount": f"{float(SALE_TOTAL) * len(product_ids):.2f}"}
            ],
        },
    )
    return response.status_code


def concurrency_phase(base: str, engine: Engine, results: Results, args) -> None:
    with engine.connect() as conn:
        hot = dict(conn.execute(text("SELECT sku, id FROM products WHERE sku LIKE 'HOT-%'")).all())
        location_id = conn.execute(
            text("SELECT id FROM locations WHERE name = 'LT Location 2'")
        ).scalar_one()
        initial = dict(
            conn.execute(
                text("SELECT product_id, quantity FROM stock_levels WHERE location_id = :l"),
                {"l": location_id},
            ).all()
        )
    a, b, c = hot["HOT-1"], hot["HOT-2"], hot["HOT-3"]
    clients = [session(base, f"lt_cashier_{n + 1}") for n in range(args.cashiers)]
    attempts = args.sales_per_cashier

    def worker(index: int) -> list[int]:
        # Even workers sell A then B, odd workers B then A: the classic lock-order deadlock.
        # Everyone also sells C on its own, so single-line oversell is covered too.
        pair = [a, b] if index % 2 == 0 else [b, a]
        codes = []
        for attempt in range(attempts):
            codes.append(sell(clients[index], pair if attempt % 2 == 0 else [c], location_id))
        return codes

    start = time.perf_counter()
    with ThreadPoolExecutor(len(clients)) as pool:
        codes = [code for batch in pool.map(worker, range(len(clients))) for code in batch]
    elapsed = time.perf_counter() - start
    for client in clients:
        client.close()

    with engine.connect() as conn:
        final = dict(
            conn.execute(
                text("SELECT product_id, quantity FROM stock_levels WHERE location_id = :l"),
                {"l": location_id},
            ).all()
        )
        sold = dict(
            conn.execute(
                text(
                    "SELECT product_id, coalesce(sum(quantity), 0) FROM sale_lines "
                    "WHERE product_id = ANY(:ids) GROUP BY product_id"
                ),
                {"ids": list(hot.values())},
            ).all()
        )
    created, rejected = codes.count(201), codes.count(409)
    other = len(codes) - created - rejected
    results.sales.append(
        f"{len(codes)} sale attempts by {len(clients)} cashiers in {elapsed:.1f} s "
        f"({len(codes) / elapsed:.1f}/s): {created} recorded, {rejected} rejected as out of "
        f"stock, {other} other"
    )
    results.check("no errors or deadlocks in concurrent sales", other == 0, f"{other} unexpected")
    for sku, product_id in hot.items():
        remaining, taken = final[product_id], sold.get(product_id, 0)
        results.check(
            f"stock consistent for {sku}",
            remaining >= 0 and remaining == initial[product_id] - taken,
            f"started {initial[product_id]}, sold {taken}, left {remaining}",
        )


def report_phase(base: str, results: Results, args: argparse.Namespace) -> None:
    client = session(base, "lt_manager")
    jobs = [
        ("valuation report (JSON)", "/api/reporting/valuation"),
        ("reorder report (JSON)", "/api/reporting/reorder"),
        ("valuation export (CSV)", "/api/reporting/valuation/export?format=csv"),
        ("valuation export (PDF)", "/api/reporting/valuation/export?format=pdf"),
        ("reorder export (CSV)", "/api/reporting/reorder/export?format=csv"),
        ("reorder export (PDF)", "/api/reporting/reorder/export?format=pdf"),
    ]
    for label, path in jobs:
        start = time.perf_counter()
        response = client.get(path)
        seconds = time.perf_counter() - start
        results.reports.append((label, seconds, len(response.content)))
        results.check(
            label,
            response.status_code == 200 and seconds < args.report_threshold,
            f"{seconds:.1f} s, {len(response.content) / 1024:.0f} KiB, HTTP {response.status_code}",
        )
    client.close()


def write_report(path: Path, results: Results, args: argparse.Namespace, rows: dict) -> None:
    lines = [
        "# Performance and load test results",
        "",
        f"Generated {datetime.now(UTC):%Y-%m-%d %H:%M} UTC by `python -m scripts.loadtest`.",
        "Re-run it to refresh this file; the profile is described in "
        "[`performance.md`](performance.md).",
        "",
        "## Dataset",
        "",
        f"- {rows['products']} products ({args.skus} catalogue SKUs plus 3 hot items), "
        f"{rows['locations']} locations, {rows['stock']} stock rows.",
        f"- {args.concurrency} concurrent API clients, {args.requests} requests per scenario, "
        f"{args.workers} uvicorn workers.",
        f"- Target: p95 under {args.threshold:g} s (NFR-1).",
        "",
        "## Search, list, filter and sort",
        "",
        "| Scenario | Requests | Median (ms) | p95 (ms) | Max (ms) | Errors |",
        "|---|---|---|---|---|---|",
    ]
    for label, count, median, p95, worst, errors in results.latency:
        lines.append(
            f"| {label} | {count} | {median * 1000:.0f} | {p95 * 1000:.0f} | "
            f"{worst * 1000:.0f} | {int(errors)} |"
        )
    lines += ["", "## Concurrent sales", ""]
    lines += [f"- {entry}" for entry in results.sales]
    lines += [
        "",
        "## Reports and exports",
        "",
        "| Report | Time (s) | Size (KiB) |",
        "|---|---|---|",
    ]
    for label, seconds, size in results.reports:
        lines.append(f"| {label} | {seconds:.1f} | {size / 1024:.0f} |")
    lines += ["", "## Checks", ""]
    lines += [f"- {'PASS' if c.passed else 'FAIL'}: {c.name} ({c.detail})" for c in results.checks]
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skus", type=int, default=10_000)
    parser.add_argument("--locations", type=int, default=5)
    parser.add_argument("--concurrency", type=int, default=10, help="parallel API clients")
    parser.add_argument("--requests", type=int, default=100, help="requests per scenario")
    parser.add_argument("--cashiers", type=int, default=8, help="concurrent cashiers")
    parser.add_argument("--sales-per-cashier", type=int, default=16)
    parser.add_argument("--workers", type=int, default=2, help="uvicorn worker processes")
    parser.add_argument("--threshold", type=float, default=2.0, help="p95 target in seconds")
    parser.add_argument("--report-threshold", type=float, default=60.0)
    parser.add_argument("--output", type=Path, default=None, help="write a Markdown report here")
    args = parser.parse_args()

    server_url = database_url()
    name = f"esims_load_{uuid.uuid4().hex[:10]}"
    admin = create_engine(server_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = server_url.set(database=name)
    engine = create_engine(url, pool_size=2)
    results = Results()
    api = None
    try:
        print(f"Seeding {args.skus} SKUs...", flush=True)
        migrate_and_seed(engine, url, args.skus, args.locations, args.cashiers)
        with engine.connect() as conn:
            rows = {
                "products": conn.execute(text("SELECT count(*) FROM products")).scalar_one(),
                "locations": conn.execute(text("SELECT count(*) FROM locations")).scalar_one(),
                "stock": conn.execute(text("SELECT count(*) FROM stock_levels")).scalar_one(),
            }
        port = free_port()
        api = start_api(url, port, args.workers)
        base = f"http://127.0.0.1:{port}"
        latency_phase(base, results, args)
        concurrency_phase(base, engine, results, args)
        report_phase(base, results, args)
        if args.output:
            write_report(args.output, results, args, rows)
    finally:
        if api:
            api.terminate()
            api.wait(timeout=30)
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()

    failed = [c for c in results.checks if not c.passed]
    print(f"\n{len(results.checks) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
