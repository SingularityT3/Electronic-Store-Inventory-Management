"""Atomic stock transfers between locations."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

import pytest
from alembic import command
from sqlalchemy import URL, create_engine, func, select, text
from sqlalchemy.orm import Session

from app.modules.audit._internal.models import AuditLog
from app.modules.auth._internal.models import User
from app.modules.product._internal.models import Category, Product, ProductVariant
from app.modules.stock._internal.models import (
    ItemCost,
    Location,
    StockLevel,
    StockMovement,
    StockTransfer,
)
from app.modules.stock.service import StockTransferError, transfer_stock
from tests.conftest import alembic_config
from tests.helpers import login


def create_transfer_data(db: Session, *, source_quantity: int = 10):
    source = Location(name="Transfer Source", type="store")
    destination = Location(name="Transfer Destination", type="warehouse")
    category = Category(name="Stock Transfer Products")
    db.add_all([source, destination, category])
    db.flush()
    product = Product(
        sku="TRANSFER-PHONE",
        name="Transfer Phone",
        category_id=category.id,
        brand="Test",
        price=Decimal("100"),
    )
    db.add(product)
    db.flush()
    db.add(
        StockLevel(
            product_id=product.id,
            location_id=source.id,
            quantity=source_quantity,
        )
    )
    db.commit()
    return source, destination, product


def test_transfer_updates_stock_movements_audit_and_valuation(client, make_user, db):
    source, destination, product = create_transfer_data(db, source_quantity=10)
    db.add(ItemCost(product_id=product.id, average_cost=Decimal("12.50")))
    db.commit()
    make_user("transfer_manager", role="manager")
    assert login(client, "transfer_manager").status_code == 200

    response = client.post(
        "/api/stock/transfers",
        json={
            "product_id": product.id,
            "from_location_id": source.id,
            "to_location_id": destination.id,
            "quantity": 4,
        },
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["product_id"] == product.id
    assert result["quantity"] == 4
    assert result["from_location_id"] == source.id
    assert result["to_location_id"] == destination.id

    levels = {
        level.location_id: level.quantity
        for level in db.scalars(select(StockLevel).where(StockLevel.product_id == product.id))
    }
    assert levels == {source.id: 6, destination.id: 4}

    transfer = db.get(StockTransfer, result["id"])
    movements = db.scalars(
        select(StockMovement).where(
            StockMovement.reference_type == "stock_transfer",
            StockMovement.reference_id == result["id"],
        )
    ).all()
    assert transfer is not None
    assert {
        (movement.location_id, movement.quantity_change, movement.movement_type)
        for movement in movements
    } == {
        (source.id, -4, "transfer_out"),
        (destination.id, 4, "transfer_in"),
    }
    audit = db.scalar(
        select(AuditLog).where(
            AuditLog.module == "stock",
            AuditLog.action == "stock_transferred",
            AuditLog.entity_id == str(result["id"]),
        )
    )
    assert audit is not None
    assert audit.before == {"from_quantity": 10, "to_quantity": 0}
    assert audit.after == {"from_quantity": 6, "to_quantity": 4}

    valuation = client.get("/api/reporting/valuation")
    assert valuation.status_code == 200, valuation.text
    product_rows = [row for row in valuation.json()["items"] if row["product_id"] == product.id]
    assert {row["location_id"]: row["quantity"] for row in product_rows} == {
        source.id: 6,
        destination.id: 4,
    }
    assert {row["location_id"]: Decimal(row["value"]) for row in product_rows} == {
        source.id: Decimal("75.00"),
        destination.id: Decimal("50.00"),
    }
    assert sum(Decimal(row["value"]) for row in product_rows) == Decimal("125.00")


def test_transfer_rejects_invalid_inputs_and_insufficient_stock(client, make_user, db):
    source, destination, product = create_transfer_data(db, source_quantity=2)
    make_user("transfer_validation_manager", role="manager")
    assert login(client, "transfer_validation_manager").status_code == 200
    endpoint = "/api/stock/transfers"
    base = {
        "product_id": product.id,
        "from_location_id": source.id,
        "to_location_id": destination.id,
        "quantity": 1,
    }

    assert client.post(endpoint, json={**base, "quantity": 0}).status_code == 422
    assert client.post(endpoint, json={**base, "to_location_id": source.id}).status_code == 422
    assert client.post(endpoint, json={**base, "product_id": 999999}).status_code == 404
    assert client.post(endpoint, json={**base, "from_location_id": 999999}).status_code == 404
    assert client.post(endpoint, json={**base, "to_location_id": 999999}).status_code == 404
    insufficient = client.post(endpoint, json={**base, "quantity": 3})
    assert insufficient.status_code == 409

    db.expire_all()
    assert (
        db.scalar(
            select(StockLevel).where(
                StockLevel.product_id == product.id,
                StockLevel.location_id == source.id,
            )
        ).quantity
        == 2
    )
    assert (
        db.scalar(
            select(StockLevel.id).where(
                StockLevel.product_id == product.id,
                StockLevel.location_id == destination.id,
            )
        )
        is None
    )
    assert db.scalar(select(func.count()).select_from(StockTransfer)) == 0
    assert db.scalar(select(func.count()).select_from(StockMovement)) == 0


def test_variant_transfer_changes_only_that_variant(client, make_user, db):
    source, destination, product = create_transfer_data(db, source_quantity=7)
    variant = ProductVariant(
        product_id=product.id,
        sku="TRANSFER-PHONE-BLACK",
        attributes={"color": "Black"},
    )
    db.add(variant)
    db.flush()
    db.add(
        StockLevel(
            product_id=product.id,
            variant_id=variant.id,
            location_id=source.id,
            quantity=3,
        )
    )
    db.commit()
    make_user("variant_transfer_manager", role="manager")
    assert login(client, "variant_transfer_manager").status_code == 200

    response = client.post(
        "/api/stock/transfers",
        json={
            "product_id": product.id,
            "variant_id": variant.id,
            "from_location_id": source.id,
            "to_location_id": destination.id,
            "quantity": 2,
        },
    )
    assert response.status_code == 201, response.text
    levels = {
        (level.variant_id, level.location_id): level.quantity
        for level in db.scalars(select(StockLevel).where(StockLevel.product_id == product.id))
    }
    assert levels == {
        (None, source.id): 7,
        (variant.id, source.id): 1,
        (variant.id, destination.id): 2,
    }


def test_transfer_permissions_and_staff_source_location_restriction(client, make_user, db):
    source, destination, product = create_transfer_data(db, source_quantity=20)
    location_response = client.get("/api/stock/transfers/locations")
    assert location_response.status_code == 401

    base = {
        "product_id": product.id,
        "from_location_id": source.id,
        "to_location_id": destination.id,
        "quantity": 1,
    }

    for role in ("admin", "manager"):
        username = f"transfer_{role}"
        make_user(username, role=role)
        assert login(client, username).status_code == 200
        transfer_locations = client.get("/api/stock/transfers/locations")
        assert transfer_locations.status_code == 200
        assert {location["id"] for location in transfer_locations.json()} >= {
            source.id,
            destination.id,
        }
        response = client.post("/api/stock/transfers", json=base)
        assert response.status_code == 201, response.text
        client.post("/api/auth/logout")

    make_user("transfer_staff_source", role="staff", location_id=source.id)
    assert login(client, "transfer_staff_source").status_code == 200
    staff_locations = client.get("/api/stock/transfers/locations")
    assert staff_locations.status_code == 200
    assert {location["id"] for location in staff_locations.json()} >= {source.id, destination.id}
    allowed = client.post("/api/stock/transfers", json=base)
    assert allowed.status_code == 201, allowed.text
    client.post("/api/auth/logout")

    make_user("transfer_staff_other", role="staff", location_id=destination.id)
    assert login(client, "transfer_staff_other").status_code == 200
    forbidden = client.post("/api/stock/transfers", json=base)
    assert forbidden.status_code == 403
    client.post("/api/auth/logout")

    make_user("transfer_cashier", role="cashier", location_id=source.id)
    assert login(client, "transfer_cashier").status_code == 200
    assert client.get("/api/stock/transfers/locations").status_code == 403
    assert client.post("/api/stock/transfers", json=base).status_code == 403


def test_transfer_rolls_back_every_write_when_audit_fails(db, make_user, monkeypatch):
    source, destination, product = create_transfer_data(db, source_quantity=5)
    user = make_user("transfer_rollback_manager", role="manager")

    def fail_record(*args, **kwargs):
        _ = (args, kwargs)
        raise RuntimeError("simulated audit failure")

    monkeypatch.setattr("app.modules.stock.service.audit_service.record", fail_record)
    with pytest.raises(RuntimeError, match="simulated audit failure"):
        transfer_stock(
            db,
            product_id=product.id,
            variant_id=None,
            from_location_id=source.id,
            to_location_id=destination.id,
            quantity=2,
            user_id=user.id,
            username=user.username,
        )

    db.expire_all()
    source_level = db.scalar(
        select(StockLevel).where(
            StockLevel.product_id == product.id,
            StockLevel.location_id == source.id,
        )
    )
    assert source_level.quantity == 5
    assert (
        db.scalar(
            select(StockLevel.id).where(
                StockLevel.product_id == product.id,
                StockLevel.location_id == destination.id,
            )
        )
        is None
    )
    assert db.scalar(select(func.count()).select_from(StockTransfer)) == 0
    assert db.scalar(select(func.count()).select_from(StockMovement)) == 0
    assert (
        db.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == "stock_transferred")
        )
        == 0
    )


def test_concurrent_transfers_cannot_overdraw_source_stock(empty_db_url: URL):
    command.upgrade(alembic_config(empty_db_url), "head")
    engine = create_engine(empty_db_url, pool_size=4)
    try:
        with Session(engine) as setup:
            source = Location(name="Concurrent Source", type="store")
            destination = Location(name="Concurrent Destination", type="warehouse")
            category = Category(name="Concurrent Transfer Products")
            setup.add_all([source, destination, category])
            setup.flush()
            product = Product(
                sku="CONCURRENT-TRANSFER",
                name="Concurrent Transfer Product",
                category_id=category.id,
                brand="Test",
                price=Decimal("20"),
            )
            user = User(
                username="concurrent_transfer_manager",
                full_name="Concurrent Transfer Manager",
                password_hash="not-used-in-service-test",
                role="manager",
            )
            setup.add_all([product, user])
            setup.flush()
            setup.add(StockLevel(product_id=product.id, location_id=source.id, quantity=1))
            setup.commit()
            source_id = source.id
            destination_id = destination.id
            product_id = product.id
            user_id = user.id

        barrier = Barrier(2)

        def execute_transfer() -> int:
            with Session(engine) as session:
                session.execute(text("SET lock_timeout = '10s'"))
                barrier.wait(timeout=10)
                try:
                    transfer_stock(
                        session,
                        product_id=product_id,
                        variant_id=None,
                        from_location_id=source_id,
                        to_location_id=destination_id,
                        quantity=1,
                        user_id=user_id,
                        username="concurrent_transfer_manager",
                    )
                    session.commit()
                    return 201
                except StockTransferError as exc:
                    session.rollback()
                    return exc.status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(execute_transfer) for _ in range(2)]
            results = [future.result(timeout=15) for future in futures]
        assert sorted(results) == [201, 409]

        with Session(engine) as verify:
            levels = {
                level.location_id: level.quantity
                for level in verify.scalars(
                    select(StockLevel).where(StockLevel.product_id == product_id)
                )
            }
            assert levels == {source_id: 0, destination_id: 1}
            assert verify.scalar(select(func.count()).select_from(StockTransfer)) == 1
            assert verify.scalar(select(func.count()).select_from(StockMovement)) == 2
    finally:
        engine.dispose()
