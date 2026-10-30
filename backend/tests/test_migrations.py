"""Migrations apply to an empty database, roll back fully, and match the models."""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import URL, create_engine, inspect, text
from sqlalchemy.exc import DBAPIError

from migrations.models import metadata
from tests.conftest import alembic_config


def _schema_objects(url: URL) -> dict[str, set[str]]:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            tables = set(inspect(conn).get_table_names()) - {"alembic_version"}
            functions = set(
                conn.scalars(
                    text(
                        "SELECT p.proname FROM pg_proc p JOIN pg_namespace n "
                        "ON n.oid = p.pronamespace WHERE n.nspname = 'public' "
                        "AND p.prokind = 'f' AND p.prolang = "
                        "(SELECT oid FROM pg_language WHERE lanname = 'plpgsql')"
                    )
                )
            )
            sequences = set(conn.scalars(text("SELECT relname FROM pg_class WHERE relkind = 'S'")))
    finally:
        engine.dispose()
    return {"tables": tables, "functions": functions, "sequences": sequences}


def test_upgrade_downgrade_upgrade(empty_db_url):
    config = alembic_config(empty_db_url)

    command.upgrade(config, "head")
    migrated = _schema_objects(empty_db_url)
    assert migrated["tables"] == set(metadata.tables)
    assert {"reject_modification", "enforce_unique_sku"} <= migrated["functions"]
    assert "invoice_number_seq" in migrated["sequences"]

    command.downgrade(config, "base")
    assert _schema_objects(empty_db_url) == {
        "tables": set(),
        "functions": set(),
        "sequences": set(),
    }

    command.upgrade(config, "head")
    assert _schema_objects(empty_db_url) == migrated


def test_models_match_migrations(migrated_engine):
    with migrated_engine.connect() as conn:
        context = MigrationContext.configure(conn, opts={"compare_type": True})
        assert compare_metadata(context, metadata) == []


def test_retention_triggers_exist_after_upgrade(migrated_engine):
    with migrated_engine.connect() as conn:
        triggers = set(conn.scalars(text("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal")))
        for table in (
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
        ):
            assert f"{table}_retention_delete" in triggers
            assert f"{table}_retention_truncate" in triggers
        assert "sales_retention_clock_immutable" in triggers
        assert "returns_retention_clock_immutable" in triggers


def test_roles_are_seeded_by_migration(conn):
    roles = set(conn.scalars(text("SELECT code FROM roles")))
    assert roles == {"admin", "manager", "staff", "cashier"}


def test_invoice_and_return_snapshots_backfill_and_reject_updates(empty_db_url):
    config = alembic_config(empty_db_url)
    command.upgrade(config, "0011")
    engine = create_engine(empty_db_url)
    with engine.begin() as conn:
        location_id = conn.execute(
            text(
                "INSERT INTO locations (name, type, address) "
                "VALUES ('Backfill Store', 'store', '1 Road') RETURNING id"
            )
        ).scalar_one()
        user_id = conn.execute(
            text(
                "INSERT INTO users (username, full_name, password_hash, role, location_id) "
                "VALUES ('backfill_cashier', 'Backfill Cashier', 'hash', 'cashier', "
                ":location_id) RETURNING id"
            ),
            {"location_id": location_id},
        ).scalar_one()
        category_id = conn.execute(
            text("INSERT INTO categories (name) VALUES ('Backfill Category') RETURNING id")
        ).scalar_one()
        product_id = conn.execute(
            text(
                "INSERT INTO products (sku, name, category_id, brand, price) "
                "VALUES ('BACKFILL-1', 'Legacy Product', :category_id, 'Brand', 100) RETURNING id"
            ),
            {"category_id": category_id},
        ).scalar_one()
        sale_id = conn.execute(
            text(
                "INSERT INTO sales (location_id, cashier_id, subtotal, tax_total, total) "
                "VALUES (:location_id, :cashier_id, 100, 18, 118) RETURNING id"
            ),
            {"location_id": location_id, "cashier_id": user_id},
        ).scalar_one()
        sale_line_id = conn.execute(
            text(
                "INSERT INTO sale_lines (sale_id, product_id, quantity, unit_price, "
                "tax_amount, line_total) "
                "VALUES (:sale_id, :product_id, 1, 100, 18, 118) RETURNING id"
            ),
            {"sale_id": sale_id, "product_id": product_id},
        ).scalar_one()
        conn.execute(
            text("INSERT INTO invoices (sale_id, total) VALUES (:sale_id, 118)"),
            {"sale_id": sale_id},
        )
        return_id = conn.execute(
            text(
                "INSERT INTO returns (sale_id, processed_by, reason, refund_total) "
                "VALUES (:sale_id, :user_id, 'Legacy return', 118) RETURNING id"
            ),
            {"sale_id": sale_id, "user_id": user_id},
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO return_lines (return_id, sale_line_id, quantity, condition, "
                "restocked, refund_amount) "
                "VALUES (:return_id, :sale_line_id, 1, 'damaged', false, 118)"
            ),
            {"return_id": return_id, "sale_line_id": sale_line_id},
        )

    command.upgrade(config, "head")
    with engine.connect() as conn:
        invoice_content = conn.execute(
            text("SELECT content FROM invoices WHERE sale_id = :sale_id"), {"sale_id": sale_id}
        ).scalar_one()
        return_content = conn.execute(
            text("SELECT content FROM returns WHERE id = :return_id"), {"return_id": return_id}
        ).scalar_one()
        assert invoice_content["backfilled"] is True
        assert invoice_content["lines"][0]["product_name"] == "Legacy Product"
        assert invoice_content["cashier_name"] == "Backfill Cashier"
        assert return_content["backfilled"] is True
        assert return_content["lines"][0]["product_name"] == "Legacy Product"

    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as conn:
        conn.execute(
            text("UPDATE invoices SET total = total WHERE sale_id = :sale_id"),
            {"sale_id": sale_id},
        )
    with pytest.raises(DBAPIError, match="immutable"), engine.begin() as conn:
        conn.execute(
            text("UPDATE returns SET content = '{}'::jsonb WHERE id = :return_id"),
            {"return_id": return_id},
        )
    engine.dispose()
