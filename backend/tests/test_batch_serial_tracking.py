"""Batch and serial inventory traceability tests for Issue #17."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import URL, create_engine, func, select, text
from sqlalchemy.orm import Session

from app.modules.auth._internal.models import User
from app.modules.product._internal.models import Category, Product
from app.modules.sales import (
    SaleTrackingError,
    restore_returned_batch_units,
    restore_returned_serials,
)
from app.modules.sales._internal.models import (
    Invoice,
    Return,
    ReturnLine,
    ReturnLineBatch,
    ReturnLineSerial,
    SaleLine,
    SaleLineBatch,
)
from app.modules.stock import (
    InsufficientStockError,
    consume_tracked_stock,
    receive_batch_stock,
    receive_serial_stock,
    transfer_stock,
    update_stock,
)
from app.modules.stock._internal.models import (
    Batch,
    BatchStock,
    Location,
    SerialNumber,
    StockLevel,
    StockMovement,
)
from tests.conftest import alembic_config
from tests.helpers import login


def setup_item(db, tracking_mode: str):
    suffix = uuid4().hex[:8]
    location = Location(name=f"Tracking location {suffix}", type="store")
    category = Category(name=f"Tracking category {suffix}")
    db.add_all([location, category])
    db.flush()
    product = Product(
        sku=f"TRACK-{suffix}",
        name=f"Tracked item {suffix}",
        category_id=category.id,
        brand="Test",
        price=Decimal("100.00"),
        tracking_mode=tracking_mode,
    )
    db.add(product)
    db.commit()
    return location, product


def record_sale(client, location_id: int, product_id: int, quantity: int, **line_fields):
    subtotal = Decimal("100.00") * quantity
    total = subtotal * Decimal("1.18")
    return client.post(
        "/api/sales",
        json={
            "location_id": location_id,
            "lines": [
                {
                    "product_id": product_id,
                    "quantity": quantity,
                    **line_fields,
                }
            ],
            "payments": [{"method": "cash", "amount": str(total)}],
        },
    )


def test_batch_receipt_sale_and_recall_reports_sold_invoice_and_available_units(
    client, make_user, db
):
    location, product = setup_item(db, "batch")
    manager = make_user("batch_manager", role="manager")
    batch_id = receive_batch_stock(
        db,
        product_id=product.id,
        variant_id=None,
        location_id=location.id,
        batch_number="BATCH-2026-08",
        quantity=100,
        user_id=manager.id,
        username=manager.username,
        reference_type="po_receipt_line",
        reference_id=1,
    )
    assert (
        receive_batch_stock(
            db,
            product_id=product.id,
            variant_id=None,
            location_id=location.id,
            batch_number="BATCH-2026-08",
            quantity=100,
            user_id=manager.id,
            username=manager.username,
            reference_type="po_receipt_line",
            reference_id=1,
        )
        == batch_id
    )
    db.commit()
    with pytest.raises(ValueError, match="tracking service"):
        update_stock(
            db,
            product_id=product.id,
            variant_id=None,
            location_id=location.id,
            quantity_delta=1,
            movement_type="receipt",
        )

    make_user("batch_cashier", role="cashier", location_id=location.id)
    assert login(client, "batch_cashier").status_code == 200
    sale = record_sale(client, location.id, product.id, 40)
    assert sale.status_code == 201, sale.text
    invoice_number = sale.json()["invoice"]["invoice_number"]
    db.commit()

    make_user("batch_view_manager", role="manager")
    client.post("/api/auth/logout")
    assert login(client, "batch_view_manager").status_code == 200
    recall = client.get(f"/api/sales/batches/{batch_id}/recall")
    assert recall.status_code == 200, recall.text
    assert recall.json()["quantity_received"] == 100
    assert recall.json()["quantity_in_stock"] == 60
    assert recall.json()["receipts"] == [
        {
            "location_id": location.id,
            "reference_type": "po_receipt_line",
            "reference_id": 1,
            "quantity": 100,
        }
    ]
    assert recall.json()["sold"] == [
        {
            "invoice_number": invoice_number,
            "quantity_sold": 40,
            "quantity_returned": 0,
            "quantity_still_sold": 40,
        }
    ]
    assert (
        db.scalar(select(BatchStock.quantity_on_hand).where(BatchStock.batch_id == batch_id)) == 60
    )
    assert (
        len(
            db.scalars(
                select(SaleLineBatch).where(
                    SaleLineBatch.sale_line_id == sale.json()["lines"][0]["id"]
                )
            ).all()
        )
        == 1
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(StockMovement)
            .where(
                StockMovement.reference_type == "po_receipt_line",
                StockMovement.reference_id == 1,
            )
        )
        == 1
    )


def test_serial_receipt_sale_and_return_preserve_invoice_trace(client, make_user, db):
    location, product = setup_item(db, "serial")
    manager = make_user("serial_manager", role="manager")
    serial_ids = receive_serial_stock(
        db,
        product_id=product.id,
        variant_id=None,
        location_id=location.id,
        serial_numbers=["SN-TV-000123"],
        user_id=manager.id,
        username=manager.username,
        reference_type="po_receipt_line",
        reference_id=123,
    )
    db.commit()

    cashier = make_user("serial_cashier", role="cashier", location_id=location.id)
    assert login(client, "serial_cashier").status_code == 200
    sale = record_sale(
        client,
        location.id,
        product.id,
        1,
        serial_numbers=["SN-TV-000123"],
    )
    assert sale.status_code == 201, sale.text
    sale_data = sale.json()
    assert sale_data["lines"][0]["serial_numbers"] == ["SN-TV-000123"]
    duplicate_sale = record_sale(
        client,
        location.id,
        product.id,
        1,
        serial_numbers=["SN-TV-000123"],
    )
    assert duplicate_sale.status_code == 422
    assert "Duplicate serial number" in duplicate_sale.text
    db.commit()

    sale_line = db.scalar(select(SaleLine).where(SaleLine.sale_id == sale_data["id"]))
    assert sale_line is not None
    return_record = Return(
        sale_id=sale_data["id"],
        processed_by=cashier.id,
        reason="Customer return",
    )
    db.add(return_record)
    db.flush()
    return_line = ReturnLine(
        return_id=return_record.id,
        sale_line_id=sale_line.id,
        quantity=1,
        condition="resaleable",
        restocked=True,
    )
    db.add(return_line)
    db.flush()
    product.is_active = False
    db.commit()
    restore_returned_serials(
        db,
        return_line_id=return_line.id,
        serial_number_ids=serial_ids,
        actor_id=cashier.id,
        actor_username=cashier.username,
    )
    db.commit()

    serial = db.get(SerialNumber, serial_ids[0])
    assert serial is not None
    assert serial.status == "returned"
    assert serial.location_id == location.id
    assert (
        db.scalar(
            select(StockLevel.quantity).where(
                StockLevel.product_id == product.id,
                StockLevel.location_id == location.id,
            )
        )
        == 1
    )
    assert (
        db.scalar(select(Invoice.invoice_number).where(Invoice.sale_id == sale_data["id"]))
        == sale_data["invoice"]["invoice_number"]
    )
    assert (
        db.scalar(
            select(StockMovement.reference_id).where(
                StockMovement.reference_type == "po_receipt_line",
                StockMovement.product_id == product.id,
            )
        )
        == 123
    )
    assert (
        db.scalar(
            select(ReturnLineSerial.serial_number_id).where(
                ReturnLineSerial.return_line_id == return_line.id
            )
        )
        == serial_ids[0]
    )


def test_duplicate_serial_receipt_returns_clear_error_and_rolls_back(db, make_user):
    location, product = setup_item(db, "serial")
    manager = make_user("duplicate_serial_manager", role="manager")
    kwargs = {
        "product_id": product.id,
        "variant_id": None,
        "location_id": location.id,
        "serial_numbers": ["SN-DUP-1"],
        "user_id": manager.id,
        "username": manager.username,
        "reference_type": "po_receipt_line",
        "reference_id": 1,
    }
    receive_serial_stock(db, **kwargs)
    db.commit()
    with pytest.raises(ValueError, match="^Duplicate serial number$"):
        receive_serial_stock(db, **kwargs)
    assert (
        db.scalar(
            select(StockLevel.quantity).where(
                StockLevel.product_id == product.id,
                StockLevel.location_id == location.id,
            )
        )
        == 1
    )
    assert (
        db.scalar(select(SerialNumber.id).where(SerialNumber.serial_number == "SN-DUP-1"))
        is not None
    )


def test_untracked_sale_needs_no_identifiers_and_mode_change_is_blocked(client, make_user, db):
    location, product = setup_item(db, "untracked")
    db.add(StockLevel(product_id=product.id, location_id=location.id, quantity=2))
    db.commit()
    cashier = make_user("untracked_cashier", role="cashier", location_id=location.id)
    assert login(client, "untracked_cashier").status_code == 200

    response = record_sale(client, location.id, product.id, 1)
    assert response.status_code == 201, response.text
    assert response.json()["lines"][0]["serial_numbers"] == []

    client.post("/api/auth/logout")
    manager = make_user("tracking_mode_manager", role="manager")
    assert login(client, "tracking_mode_manager").status_code == 200
    update = client.put(
        f"/api/product/{product.id}",
        json={
            "name": product.name,
            "sku": product.sku,
            "category_id": product.category_id,
            "brand": product.brand,
            "price": "100.00",
            "description": None,
            "tracking_mode": "batch",
        },
    )
    assert update.status_code == 409
    assert cashier.role == "cashier"
    assert manager.role == "manager"


def test_legacy_product_update_preserves_tracking_mode_and_invalid_mode_is_rejected(
    client, make_user, db
):
    _, product = setup_item(db, "serial")
    manager = make_user("tracking_compat_manager", role="manager")
    assert login(client, "tracking_compat_manager").status_code == 200
    body = {
        "name": product.name,
        "sku": product.sku,
        "category_id": product.category_id,
        "brand": product.brand,
        "price": "100.00",
        "description": None,
    }

    legacy_update = client.put(f"/api/product/{product.id}", json=body)
    assert legacy_update.status_code == 200, legacy_update.text
    assert legacy_update.json()["tracking_mode"] == "serial"

    invalid_update = client.put(
        f"/api/product/{product.id}",
        json={**body, "tracking_mode": "lot"},
    )
    assert invalid_update.status_code == 422
    null_update = client.put(
        f"/api/product/{product.id}",
        json={**body, "tracking_mode": None},
    )
    assert null_update.status_code == 422
    assert manager.role == "manager"


def test_batch_return_restores_stock_and_keeps_invoice_allocation(client, make_user, db):
    location, product = setup_item(db, "batch")
    manager = make_user("batch_return_manager", role="manager")
    batch_id = receive_batch_stock(
        db,
        product_id=product.id,
        variant_id=None,
        location_id=location.id,
        batch_number="BATCH-RETURN",
        quantity=3,
        user_id=manager.id,
        username=manager.username,
        reference_type="po_receipt_line",
        reference_id=55,
    )
    db.commit()
    cashier = make_user("batch_return_cashier", role="cashier", location_id=location.id)
    assert login(client, "batch_return_cashier").status_code == 200
    sale = record_sale(client, location.id, product.id, 2)
    assert sale.status_code == 201, sale.text
    sale_data = sale.json()
    db.commit()
    sale_line = db.scalar(select(SaleLine).where(SaleLine.sale_id == sale_data["id"]))
    assert sale_line is not None
    return_record = Return(
        sale_id=sale_data["id"],
        processed_by=cashier.id,
        reason="Batch item return",
    )
    db.add(return_record)
    db.flush()
    return_line = ReturnLine(
        return_id=return_record.id,
        sale_line_id=sale_line.id,
        quantity=1,
        condition="resaleable",
        restocked=True,
    )
    db.add(return_line)
    db.flush()
    restore_returned_batch_units(
        db,
        return_line_id=return_line.id,
        actor_id=cashier.id,
        actor_username=cashier.username,
    )
    db.commit()
    with pytest.raises(SaleTrackingError, match="already been restocked"):
        restore_returned_batch_units(
            db,
            return_line_id=return_line.id,
            actor_id=cashier.id,
            actor_username=cashier.username,
        )
    db.rollback()
    allocation = db.scalar(select(SaleLineBatch).where(SaleLineBatch.sale_line_id == sale_line.id))
    assert allocation is not None
    assert (
        db.scalar(
            select(ReturnLineBatch.quantity).where(ReturnLineBatch.return_line_id == return_line.id)
        )
        == 1
    )

    client.post("/api/auth/logout")
    assert login(client, "batch_return_manager").status_code == 200
    recall = client.get(f"/api/sales/batches/{batch_id}/recall")
    assert recall.status_code == 200, recall.text
    assert recall.json()["quantity_in_stock"] == 2
    assert recall.json()["quantity_received"] == 3
    assert len(recall.json()["receipts"]) == 1
    assert recall.json()["sold"] == [
        {
            "invoice_number": sale_data["invoice"]["invoice_number"],
            "quantity_sold": 2,
            "quantity_returned": 1,
            "quantity_still_sold": 1,
        }
    ]


def test_batch_recall_is_limited_to_staff_location(client, make_user, db):
    location, product = setup_item(db, "batch")
    other = Location(name=f"Other tracking location {uuid4().hex[:8]}", type="store")
    db.add(other)
    db.flush()
    manager = make_user("batch_scope_manager", role="manager")
    batch_id = receive_batch_stock(
        db,
        product_id=product.id,
        variant_id=None,
        location_id=location.id,
        batch_number="BATCH-SCOPE",
        quantity=2,
        user_id=manager.id,
        username=manager.username,
        reference_type="receipt",
        reference_id=1,
    )
    receive_batch_stock(
        db,
        product_id=product.id,
        variant_id=None,
        location_id=other.id,
        batch_number="BATCH-SCOPE",
        quantity=3,
        user_id=manager.id,
        username=manager.username,
        reference_type="receipt",
        reference_id=2,
    )
    db.commit()
    make_user("batch_scope_staff", role="staff", location_id=location.id)
    assert login(client, "batch_scope_staff").status_code == 200
    recall = client.get(f"/api/sales/batches/{batch_id}/recall")
    assert recall.status_code == 200, recall.text
    assert recall.json()["quantity_in_stock"] == 2
    assert recall.json()["locations"] == [{"location_id": location.id, "quantity_in_stock": 2}]
    assert (
        client.get(f"/api/sales/batches/{batch_id}/recall?location_id={other.id}").status_code
        == 403
    )
    client.post("/api/auth/logout")
    make_user("batch_scope_cashier", role="cashier", location_id=location.id)
    assert login(client, "batch_scope_cashier").status_code == 200
    assert client.get(f"/api/sales/batches/{batch_id}/recall").status_code == 403


def test_batch_and_serial_transfers_keep_tracked_and_quantity_stock_aligned(db, make_user):
    source, batch_product = setup_item(db, "batch")
    destination = Location(name=f"Destination {uuid4().hex[:8]}", type="warehouse")
    db.add(destination)
    db.flush()
    manager = make_user("tracked_transfer_manager", role="manager")
    batch_id = receive_batch_stock(
        db,
        product_id=batch_product.id,
        variant_id=None,
        location_id=source.id,
        batch_number="BATCH-MOVE",
        quantity=3,
        user_id=manager.id,
        username=manager.username,
        reference_type="receipt",
        reference_id=11,
    )

    _, serial_product = setup_item(db, "serial")
    receive_serial_stock(
        db,
        product_id=serial_product.id,
        variant_id=None,
        location_id=source.id,
        serial_numbers=["SN-MOVE-1"],
        user_id=manager.id,
        username=manager.username,
        reference_type="receipt",
        reference_id=12,
    )
    db.commit()

    transfer_stock(
        db,
        product_id=batch_product.id,
        variant_id=None,
        from_location_id=source.id,
        to_location_id=destination.id,
        quantity=2,
        user_id=manager.id,
        username=manager.username,
    )
    transfer_stock(
        db,
        product_id=serial_product.id,
        variant_id=None,
        from_location_id=source.id,
        to_location_id=destination.id,
        quantity=1,
        user_id=manager.id,
        username=manager.username,
    )
    db.commit()

    assert (
        db.scalar(
            select(BatchStock.quantity_on_hand).where(
                BatchStock.batch_id == batch_id, BatchStock.location_id == source.id
            )
        )
        == 1
    )
    assert (
        db.scalar(
            select(BatchStock.quantity_on_hand).where(
                BatchStock.batch_id == batch_id, BatchStock.location_id == destination.id
            )
        )
        == 2
    )
    assert (
        db.scalar(
            select(StockLevel.quantity).where(
                StockLevel.product_id == batch_product.id,
                StockLevel.location_id == source.id,
            )
        )
        == 1
    )
    assert (
        db.scalar(
            select(StockLevel.quantity).where(
                StockLevel.product_id == batch_product.id,
                StockLevel.location_id == destination.id,
            )
        )
        == 2
    )
    assert (
        db.scalar(select(SerialNumber.location_id).where(SerialNumber.serial_number == "SN-MOVE-1"))
        == destination.id
    )
    assert (
        db.scalar(
            select(StockLevel.quantity).where(
                StockLevel.product_id == serial_product.id,
                StockLevel.location_id == source.id,
            )
        )
        == 0
    )
    assert (
        db.scalar(
            select(StockLevel.quantity).where(
                StockLevel.product_id == serial_product.id,
                StockLevel.location_id == destination.id,
            )
        )
        == 1
    )


@pytest.mark.parametrize("tracking_mode", ["batch", "serial"])
def test_concurrent_tracked_sales_cannot_sell_last_unit_twice(
    empty_db_url: URL, tracking_mode: str
):
    command.upgrade(alembic_config(empty_db_url), "head")
    engine = create_engine(empty_db_url, pool_size=4)
    try:
        with Session(engine) as setup:
            location = Location(name=f"Concurrent {tracking_mode} store", type="store")
            category = Category(name=f"Concurrent {tracking_mode} products")
            user = User(
                username=f"concurrent_{tracking_mode}",
                full_name="Concurrent Sale User",
                password_hash="not-used-in-service-test",
                role="manager",
            )
            setup.add_all([location, category, user])
            setup.flush()
            product = Product(
                sku=f"CONCURRENT-{tracking_mode}",
                name=f"Concurrent {tracking_mode} product",
                category_id=category.id,
                brand="Test",
                price=Decimal("10.00"),
                tracking_mode=tracking_mode,
            )
            setup.add(product)
            setup.flush()
            setup.add(StockLevel(product_id=product.id, location_id=location.id, quantity=1))
            if tracking_mode == "batch":
                batch = Batch(product_id=product.id, batch_number="CONCURRENT-BATCH")
                setup.add(batch)
                setup.flush()
                setup.add(
                    BatchStock(
                        batch_id=batch.id,
                        location_id=location.id,
                        quantity_received=1,
                        quantity_on_hand=1,
                    )
                )
                serial_numbers: tuple[str, ...] = ()
            else:
                setup.add(
                    SerialNumber(
                        serial_number="CONCURRENT-SERIAL",
                        product_id=product.id,
                        location_id=location.id,
                        status="in_stock",
                    )
                )
                serial_numbers = ("CONCURRENT-SERIAL",)
            setup.commit()
            location_id = location.id
            product_id = product.id
            user_id = user.id

        barrier = Barrier(2)

        def sell_last_unit(sale_id: int) -> str:
            with Session(engine) as session:
                session.execute(text("SET lock_timeout = '10s'"))
                barrier.wait(timeout=10)
                try:
                    consume_tracked_stock(
                        session,
                        product_id=product_id,
                        variant_id=None,
                        location_id=location_id,
                        quantity=1,
                        serial_numbers=serial_numbers,
                        user_id=user_id,
                        username="concurrent_test",
                        sale_id=sale_id,
                    )
                    session.commit()
                    return "sold"
                except (InsufficientStockError, ValueError):
                    session.rollback()
                    return "rejected"

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(sell_last_unit, (101, 102)))
        assert sorted(results) == ["rejected", "sold"]

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
            assert (
                verify.scalar(
                    select(func.count())
                    .select_from(StockMovement)
                    .where(StockMovement.product_id == product_id)
                )
                == 1
            )
            if tracking_mode == "batch":
                assert (
                    verify.scalar(
                        select(BatchStock.quantity_on_hand)
                        .join(Batch, Batch.id == BatchStock.batch_id)
                        .where(Batch.product_id == product_id)
                    )
                    == 0
                )
            else:
                assert (
                    verify.scalar(
                        select(SerialNumber.status).where(SerialNumber.product_id == product_id)
                    )
                    == "sold"
                )
    finally:
        engine.dispose()
