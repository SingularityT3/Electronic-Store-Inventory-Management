import gzip
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from app.config import Settings
from scripts.backup import Config, check_job
from scripts.retention import TABLES, archive


def test_retention_configuration_has_eight_year_minimum():
    assert Settings().retention_years == 8
    assert Settings(retention_years=10).retention_years == 10
    with pytest.raises(ValidationError, match="greater than or equal to 8"):
        Settings(retention_years=7)


def test_backup_monthly_default_tracks_retention():
    assert Config.from_env({"RETENTION_YEARS": "10"}).keep_monthly == 120
    assert (
        Config.from_env({"RETENTION_YEARS": "10", "BACKUP_KEEP_MONTHLY": "144"}).keep_monthly == 144
    )


def test_backup_check_rejects_monthly_window_below_retention(tmp_path: Path):
    assert not check_job(
        Config(backup_dir=tmp_path, keep_monthly=95, retention_years=8), alert=False
    )


def test_retention_script_covers_every_sale_and_return_table():
    assert set(TABLES) == {
        "sales",
        "sale_lines",
        "sale_line_serials",
        "sale_line_batches",
        "payments",
        "returns",
        "return_lines",
        "return_line_serials",
        "return_line_batches",
        "invoices",
    }


def test_sales_routes_have_no_delete_handlers_or_delete_statements():
    sales_dir = Path(__file__).parents[1] / "app" / "modules" / "sales"
    source = "\n".join(path.read_text(encoding="utf-8") for path in sales_dir.rglob("*.py"))
    assert "@router.delete" not in source
    assert "db.delete(" not in source
    assert "DELETE FROM sales" not in source
    assert "DELETE FROM invoices" not in source


def test_retention_archive_dry_run_then_execute_is_verified_and_repeatable(db, tmp_path):
    location = db.execute(
        text("INSERT INTO locations (name, type) VALUES ('Archive Store', 'store') RETURNING id")
    ).scalar_one()
    user = db.execute(
        text(
            "INSERT INTO users (username, full_name, password_hash, role) "
            "VALUES ('archive_user', 'Archive User', 'x', 'admin') RETURNING id"
        )
    ).scalar_one()
    sold_at = datetime.now(UTC) - timedelta(days=365 * 9 + 5)
    sale_id = db.execute(
        text(
            "INSERT INTO sales (location_id, cashier_id, subtotal, tax_total, total, sold_at) "
            "VALUES (:loc, :user, 100, 18, 118, :date) RETURNING id"
        ),
        {"loc": location, "user": user, "date": sold_at},
    ).scalar_one()
    db.execute(
        text("INSERT INTO invoices (sale_id, total, issued_at) VALUES (:id, 118, :date)"),
        {"id": sale_id, "date": sold_at},
    )
    db.commit()

    assert archive(db, 8, tmp_path, execute=False, limit=500) == 1
    assert (
        db.execute(text("SELECT count(*) FROM sales WHERE id=:id"), {"id": sale_id}).scalar_one()
        == 1
    )
    assert archive(db, 8, tmp_path, execute=True, limit=500) == 1
    files = list(tmp_path.glob("sale-*.jsonl.gz"))
    assert len(files) == 1
    archive_file = files[0]
    digest = hashlib.sha256(archive_file.read_bytes()).hexdigest()
    assert (tmp_path / f"{archive_file.name}.sha256").read_text().startswith(digest)
    with gzip.open(archive_file, "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    assert {row["table"] for row in rows} == {"sales", "invoices"}
    assert (
        db.execute(text("SELECT count(*) FROM sales WHERE id=:id"), {"id": sale_id}).scalar_one()
        == 0
    )
    assert archive(db, 8, tmp_path, execute=True, limit=500) == 0
