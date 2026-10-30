"""Report and archive expired sales: python -m scripts.retention report|archive."""

import argparse
import gzip
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text

from app.config import get_settings
from app.db import get_session
from app.modules.audit import audit_service

TABLES = (
    "return_line_serials",
    "return_line_batches",
    "return_lines",
    "returns",
    "sale_line_serials",
    "sale_line_batches",
    "payments",
    "invoices",
    "sale_lines",
    "sales",
)


def _expired_clause(years: int) -> str:
    return "sold_at + make_interval(years => :years) <= now()"


def report(db, years: int) -> None:
    clause = _expired_clause(years)
    row = (
        db.execute(
            text(f"""
        SELECT count(*) AS total,
               count(*) FILTER (WHERE {clause}) AS expired,
               min(sold_at) AS oldest, max(sold_at) AS newest,
               min(sold_at + make_interval(years => :years))
                   FILTER (WHERE sold_at + make_interval(years => :years) > now()) AS next_expiry
        FROM sales
    """),
            {"years": years},
        )
        .mappings()
        .one()
    )
    return_counts = (
        db.execute(
            text("""
            SELECT count(*) AS total,
                   count(*) FILTER (
                       WHERE created_at + make_interval(years => :years) <= now()
                   ) AS expired
            FROM returns
        """),
            {"years": years},
        )
        .mappings()
        .one()
    )
    invoice_counts = (
        db.execute(
            text("""
            SELECT count(*) AS total,
                   count(*) FILTER (
                       WHERE issued_at + make_interval(years => :years) <= now()
                   ) AS expired
            FROM invoices
        """),
            {"years": years},
        )
        .mappings()
        .one()
    )
    print(
        json.dumps(
            {"sales": dict(row), "returns": dict(return_counts), "invoices": dict(invoice_counts)},
            default=str,
            indent=2,
        )
    )


def _sale_rows(db, sale_id: int) -> dict[str, list[dict]]:
    predicates = {
        "sales": ("id = :sid", ""),
        "sale_lines": ("sale_id = :sid", ""),
        "sale_line_serials": ("sale_line_id IN (SELECT id FROM sale_lines WHERE sale_id=:sid)", ""),
        "sale_line_batches": ("sale_line_id IN (SELECT id FROM sale_lines WHERE sale_id=:sid)", ""),
        "payments": ("sale_id = :sid", ""),
        "invoices": ("sale_id = :sid", ""),
        "returns": ("sale_id = :sid", ""),
        "return_lines": ("return_id IN (SELECT id FROM returns WHERE sale_id=:sid)", ""),
        "return_line_serials": (
            "return_line_id IN (SELECT id FROM return_lines WHERE return_id IN (SELECT id FROM returns WHERE sale_id=:sid))",  # noqa: E501
            "",
        ),
        "return_line_batches": (
            "return_line_id IN (SELECT id FROM return_lines WHERE return_id IN (SELECT id FROM returns WHERE sale_id=:sid))",  # noqa: E501
            "",
        ),
    }
    return {
        table: [
            dict(r)
            for r in db.execute(
                text(f"SELECT * FROM {table} WHERE {predicates[table][0]}"), {"sid": sale_id}
            ).mappings()
        ]
        for table in TABLES
    }


def archive(db, years: int, path: Path, *, execute: bool, limit: int) -> int:
    print("Take and verify a full database backup before archiving.")
    ids = db.scalars(
        text(
            f"SELECT id FROM sales WHERE {_expired_clause(years)} AND NOT EXISTS (SELECT 1 FROM returns r WHERE r.sale_id=sales.id AND r.created_at + make_interval(years => :years) > now()) ORDER BY sold_at, id LIMIT :limit"  # noqa: E501
        ),
        {"years": years, "limit": limit},
    ).all()
    if not execute:
        print(f"Dry run: {len(ids)} expired sale(s) would be archived: {ids}")
        return len(ids)
    path.mkdir(parents=True, exist_ok=True)
    for sale_id in ids:
        rows = _sale_rows(db, sale_id)
        oldest = rows["sales"][0]["sold_at"]
        newest = max((r["created_at"] for r in rows["returns"]), default=oldest)
        name = f"sale-{sale_id}-{datetime.now(UTC):%Y%m%dT%H%M%SZ}.jsonl.gz"
        dest = path / name
        with gzip.open(dest, "wt", encoding="utf-8") as stream:
            for table, values in rows.items():
                for value in values:
                    stream.write(json.dumps({"table": table, "row": value}, default=str) + "\n")
        digest = hashlib.sha256(dest.read_bytes()).hexdigest()
        (path / f"{name}.sha256").write_text(digest + "  " + name + "\n", encoding="ascii")
        if hashlib.sha256(dest.read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"Archive verification failed: {name}")
        with gzip.open(dest, "rt", encoding="utf-8") as stream:
            archived = [json.loads(line) for line in stream]
        archived_counts = {table: 0 for table in TABLES}
        for item in archived:
            if item.get("table") not in archived_counts:
                raise RuntimeError(f"Unexpected table in archive: {name}")
            archived_counts[item["table"]] += 1
        counts = {table: len(values) for table, values in rows.items()}
        if archived_counts != counts or sum(archived_counts.values()) != len(archived):
            raise RuntimeError(f"Archive row count verification failed: {name}")
        with db.begin_nested():
            for table in TABLES:
                db.execute(
                    text(
                        f"DELETE FROM {table} WHERE "
                        + {
                            "return_line_serials": "return_line_id IN (SELECT id FROM return_lines WHERE return_id IN (SELECT id FROM returns WHERE sale_id=:sid))",  # noqa: E501
                            "return_line_batches": "return_line_id IN (SELECT id FROM return_lines WHERE return_id IN (SELECT id FROM returns WHERE sale_id=:sid))",  # noqa: E501
                            "return_lines": "return_id IN (SELECT id FROM returns WHERE sale_id=:sid)",  # noqa: E501
                            "returns": "sale_id=:sid",
                            "sale_line_serials": "sale_line_id IN (SELECT id FROM sale_lines WHERE sale_id=:sid)",  # noqa: E501
                            "sale_line_batches": "sale_line_id IN (SELECT id FROM sale_lines WHERE sale_id=:sid)",  # noqa: E501
                            "payments": "sale_id=:sid",
                            "invoices": "sale_id=:sid",
                            "sale_lines": "sale_id=:sid",
                            "sales": "id=:sid",
                        }[table]
                    ),
                    {"sid": sale_id},
                )
            audit_service.record(
                db,
                module="sales",
                action="retention_archive_executed",
                entity_type="sale",
                entity_id=str(sale_id),
                details=json.dumps(
                    {
                        "counts": counts,
                        "oldest": str(oldest),
                        "newest": str(newest),
                        "archive": name,
                    }
                ),
            )
        db.commit()
    print(f"Archived {len(ids)} sale(s).")
    return len(ids)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("report")
    cmd = sub.add_parser("archive")
    cmd.add_argument("--execute", action="store_true")
    cmd.add_argument("--limit", type=int, default=500)
    args = parser.parse_args(argv)
    settings = get_settings()
    with next(get_session()) as db:
        if args.command == "report":
            report(db, settings.retention_years)
        else:
            archive(
                db,
                settings.retention_years,
                Path(settings.retention_archive_path),
                execute=args.execute,
                limit=args.limit,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
