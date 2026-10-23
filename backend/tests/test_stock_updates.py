"""Shared transactional stock quantity updates."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

import pytest
from alembic import command
from sqlalchemy import URL, create_engine, func, select, text
from sqlalchemy.orm import Session

from app.modules.audit._internal.models import AuditLog
from app.modules.product._internal.models import Category, Product, ProductVariant
from app.modules.stock._internal.models import Location, StockLevel, StockMovement
from app.modules.stock.service import InsufficientStockError, update_stock
from tests.conftest import alembic_config


def create_stock_item(db: Session, *, quantity: int = 10):
    location = Location(name="Shared Update Store", type="store")
    other_location = Location(name="Shared Update Warehouse", type="warehouse")
    category = Category(name="Shared Update Products")
    db.add_all([location, other_location, category])
    db.flush()
    product = Product(
        sku="SHARED-UPDATE-PHONE",
        name="Shared Update Phone",
        category_id=category.id,
        brand="Test",
        price=Decimal("100"),
    )
    db.add(product)
    db.flush()
    db.add(StockLevel(product_id=product.id, location_id=location.id, quantity=quantity))
    db.commit()
    return location, other_location, product


def test_update_stock_changes_existing_quantity_and_records_movement_and_audit(db):
    location, _, product = create_stock_item(db, quantity=10)

    result = update_stock(
        db,
        product_id=product.id,
        variant_id=None,
        location_id=location.id,
        quantity_delta=-3,
        movement_type="sale",
        user_id=None,
        username="stock_counter",
        reference_type="sale",
        reference_id=42,
    )

    assert result.quantity_delta == -3
    assert result.previous_quantity == 10
    assert result.quantity == 7
    level = db.scalar(
        select(StockLevel).where(
            StockLevel.product_id == product.id,
            StockLevel.variant_id.is_(None),
            StockLevel.location_id == location.id,
        )
    )
    assert level.quantity == 7
    movement = db.scalar(select(StockMovement).where(StockMovement.reference_type == "sale"))
    assert movement is not None
    assert movement.quantity_change == -3
    assert movement.movement_type == "sale"
    assert movement.reference_id == 42
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "stock_updated"))
    assert audit is not None
    assert audit.username == "stock_counter"
    assert audit.before == {"quantity": 10}
    assert audit.after == {"quantity": 7, "quantity_delta": -3}


def test_positive_delta_creates_missing_location_row_without_changing_other_stock(db):
    location, other_location, product = create_stock_item(db, quantity=10)
    variant = ProductVariant(
        product_id=product.id,
        sku="SHARED-UPDATE-PHONE-BLACK",
        attributes={"color": "Black"},
    )
    db.add(variant)
    db.flush()
    db.add(
        StockLevel(
            product_id=product.id,
            variant_id=variant.id,
            location_id=location.id,
            quantity=4,
        )
    )
    db.commit()

    result = update_stock(
        db,
        product_id=product.id,
        variant_id=variant.id,
        location_id=other_location.id,
        quantity_delta=5,
        movement_type="receipt",
    )

    assert result.previous_quantity == 0
    assert result.quantity == 5
    levels = {
        (level.variant_id, level.location_id): level.quantity
        for level in db.scalars(select(StockLevel).where(StockLevel.product_id == product.id))
    }
    assert levels == {
        (None, location.id): 10,
        (variant.id, location.id): 4,
        (variant.id, other_location.id): 5,
    }


def test_update_stock_rejects_zero_and_inconsistent_movement_direction(db):
    location, _, product = create_stock_item(db)
    common = {
        "product_id": product.id,
        "variant_id": None,
        "location_id": location.id,
    }

    with pytest.raises(ValueError, match="must not be zero"):
        update_stock(**common, db=db, quantity_delta=0, movement_type="receipt")
    with pytest.raises(ValueError, match="must decrease stock"):
        update_stock(**common, db=db, quantity_delta=1, movement_type="sale")
    with pytest.raises(ValueError, match="must increase stock"):
        update_stock(**common, db=db, quantity_delta=-1, movement_type="receipt")


def test_insufficient_stock_and_missing_row_leave_stock_and_log_unchanged(db):
    location, other_location, product = create_stock_item(db, quantity=2)
    for target_location, delta in ((location.id, -3), (other_location.id, -1)):
        with pytest.raises(InsufficientStockError, match="Insufficient stock"):
            update_stock(
                db,
                product_id=product.id,
                variant_id=None,
                location_id=target_location,
                quantity_delta=delta,
                movement_type="sale",
            )

    level = db.scalar(
        select(StockLevel).where(
            StockLevel.product_id == product.id,
            StockLevel.location_id == location.id,
        )
    )
    assert level.quantity == 2
    assert (
        db.scalar(
            select(StockLevel.id).where(
                StockLevel.product_id == product.id,
                StockLevel.location_id == other_location.id,
            )
        )
        is None
    )
    assert db.scalar(select(func.count()).select_from(StockMovement)) == 0
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0


def test_update_rolls_back_balance_movement_and_audit_when_recording_fails(db, monkeypatch):
    location, _, product = create_stock_item(db, quantity=8)

    def fail_record(*args, **kwargs):
        _ = (args, kwargs)
        raise RuntimeError("simulated audit failure")

    monkeypatch.setattr("app.modules.stock.service.audit_service.record", fail_record)
    with pytest.raises(RuntimeError, match="simulated audit failure"):
        update_stock(
            db,
            product_id=product.id,
            variant_id=None,
            location_id=location.id,
            quantity_delta=-2,
            movement_type="adjustment",
            reason_code="correction",
            reason="test rollback",
        )

    db.expire_all()
    level = db.scalar(
        select(StockLevel).where(
            StockLevel.product_id == product.id,
            StockLevel.location_id == location.id,
        )
    )
    assert level.quantity == 8
    assert db.scalar(select(func.count()).select_from(StockMovement)) == 0
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0


def test_update_participates_in_callers_transaction(db):
    location, _, product = create_stock_item(db, quantity=6)

    result = update_stock(
        db,
        product_id=product.id,
        variant_id=None,
        location_id=location.id,
        quantity_delta=-2,
        movement_type="adjustment",
        reason_code="correction",
        reason="caller transaction test",
    )
    assert result.quantity == 4
    assert (
        db.scalar(
            select(StockLevel.quantity).where(
                StockLevel.product_id == product.id,
                StockLevel.location_id == location.id,
            )
        )
        == 4
    )

    db.rollback()
    assert (
        db.scalar(
            select(StockLevel.quantity).where(
                StockLevel.product_id == product.id,
                StockLevel.location_id == location.id,
            )
        )
        == 6
    )
    assert db.scalar(select(func.count()).select_from(StockMovement)) == 0
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0


def test_concurrent_updates_serialize_without_overselling_or_lost_increments(
    empty_db_url: URL,
):
    command.upgrade(alembic_config(empty_db_url), "head")
    engine = create_engine(empty_db_url, pool_size=8)
    try:
        with Session(engine) as setup:
            location = Location(name="Concurrent Update Store", type="store")
            category = Category(name="Concurrent Update Products")
            setup.add_all([location, category])
            setup.flush()
            product = Product(
                sku="CONCURRENT-UPDATE-PHONE",
                name="Concurrent Update Phone",
                category_id=category.id,
                brand="Test",
                price=Decimal("50"),
            )
            setup.add(product)
            setup.flush()
            setup.add(
                StockLevel(
                    product_id=product.id,
                    location_id=location.id,
                    quantity=1,
                )
            )
            setup.commit()
            product_id = product.id
            location_id = location.id

        def concurrent_decrease() -> str:
            with Session(engine) as session:
                session.execute(text("SET lock_timeout = '10s'"))
                barrier.wait(timeout=10)
                try:
                    update_stock(
                        session,
                        product_id=product_id,
                        variant_id=None,
                        location_id=location_id,
                        quantity_delta=-1,
                        movement_type="sale",
                    )
                    session.commit()
                    return "updated"
                except InsufficientStockError:
                    session.rollback()
                    return "insufficient"

        barrier = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda _: concurrent_decrease(), range(2)))
        assert sorted(outcomes) == ["insufficient", "updated"]

        with Session(engine) as verify:
            assert (
                verify.scalar(
                    select(StockLevel.quantity).where(
                        StockLevel.product_id == product_id,
                        StockLevel.location_id == location_id,
                    )
                )
                == 0
            )
            assert verify.scalar(select(func.count()).select_from(StockMovement)) == 1

        increment_barrier = Barrier(8)

        def concurrent_increments() -> None:
            with Session(engine) as session:
                session.execute(text("SET lock_timeout = '10s'"))
                increment_barrier.wait(timeout=10)
                for _ in range(5):
                    update_stock(
                        session,
                        product_id=product_id,
                        variant_id=None,
                        location_id=location_id,
                        quantity_delta=1,
                        movement_type="receipt",
                    )
                session.commit()

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(concurrent_increments) for _ in range(8)]
            for future in futures:
                future.result(timeout=30)

        with Session(engine) as verify:
            assert (
                verify.scalar(
                    select(StockLevel.quantity).where(
                        StockLevel.product_id == product_id,
                        StockLevel.location_id == location_id,
                    )
                )
                == 40
            )
            assert verify.scalar(select(func.count()).select_from(StockMovement)) == 41
    finally:
        engine.dispose()
