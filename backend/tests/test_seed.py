from sqlalchemy import text

from app.modules.auth._internal.passwords import verify_password
from scripts.seed import PRODUCTS, USERS, seed


def _count(conn, table: str) -> int:
    return conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()


def test_seed_is_repeatable(migrated_engine):
    seed(migrated_engine, "seed-test-password")
    with migrated_engine.connect() as conn:
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

    seed(migrated_engine, "seed-test-password")
    with migrated_engine.connect() as conn:
        assert {t: _count(conn, t) for t in first} == first
        assert first["products"] == len(PRODUCTS)
        assert _count(conn, "users") == len(USERS)
        admin_hash = conn.execute(
            text("SELECT password_hash FROM users WHERE username = 'admin' AND role = 'admin'")
        ).scalar_one()
    assert verify_password(admin_hash, "seed-test-password")
