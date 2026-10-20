"""Migrations apply to an empty database, roll back fully, and match the models."""

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import URL, create_engine, inspect, text

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


def test_roles_are_seeded_by_migration(conn):
    roles = set(conn.scalars(text("SELECT code FROM roles")))
    assert roles == {"admin", "manager", "staff", "cashier"}
