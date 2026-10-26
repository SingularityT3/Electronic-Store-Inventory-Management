from collections.abc import Iterator

import pytest
from alembic import command
from sqlalchemy import Engine, create_engine, text

from app.modules.auth._internal.passwords import verify_password
from scripts.seed import PRODUCTS, USERS, seed
from tests.conftest import alembic_config, throwaway_database


@pytest.fixture
def seed_engine() -> Iterator[Engine]:
    """A database of its own: the seed commits, so its rows must not reach other tests."""
    with throwaway_database() as url:
        command.upgrade(alembic_config(url), "head")
        engine = create_engine(url)
        yield engine
        engine.dispose()


def _count(conn, table: str) -> int:
    return conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()


def test_seed_is_repeatable(seed_engine):
    seed(seed_engine, "seed-test-password")
    with seed_engine.connect() as conn:
        first = {
            t: _count(conn, t)
            for t in ("products", "product_variants", "stock_levels", "stock_alerts")
        }
        # Every fourth item is low at the first store, and has its alert.
        low_levels = conn.execute(
            text("SELECT count(*) FROM stock_levels WHERE quantity <= reorder_threshold")
        ).scalar_one()
        assert low_levels > 0
        assert first["stock_alerts"] == low_levels

    seed(seed_engine, "seed-test-password")
    with seed_engine.connect() as conn:
        assert {t: _count(conn, t) for t in first} == first
        assert first["products"] == len(PRODUCTS)
        assert _count(conn, "users") == len(USERS)
        admin_hash = conn.execute(
            text("SELECT password_hash FROM users WHERE username = 'admin' AND role = 'admin'")
        ).scalar_one()
    assert verify_password(admin_hash, "seed-test-password")
