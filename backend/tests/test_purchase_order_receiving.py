"""Purchase order receiving API tests for Issue #22."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from uuid import uuid4

from alembic import command
from fastapi import HTTPException
from sqlalchemy import URL, create_engine, func, select, text
from sqlalchemy.orm import Session

from app.modules.audit._internal.models import AuditLog
from app.modules.auth._internal.models import User
from app.modules.auth.service import CurrentUser
from app.modules.notifications._internal.models import Notification
from app.modules.product._internal.models import Category, Product
from app.modules.purchasing._internal.models import (
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseOrderReceipt,
    PurchaseOrderReceiptLine,
    PurchaseOrderReceiptSerial,
    Supplier,
    SupplierPriceHistory,
)
from app.modules.purchasing.purchase_orders import (
    PurchaseOrderReceiptInput,
    PurchaseOrderReceiptLineInput,
    receive_purchase_order,
)
from app.modules.stock._internal.models import (
    Batch,
    BatchReceipt,
    BatchStock,
    ItemCost,
    Location,
    SerialNumber,
    StockLevel,
    StockMovement,
)
from tests.conftest import alembic_config
from tests.helpers import login


def create_order(
    db: Session,
    creator: User,
    *,
    ordered: int = 50,
    tracking_mode: str = "untracked",
    suffix: str | None = None,
) -> tuple[PurchaseOrder, PurchaseOrderLine, Product, Location, Supplier]:
    suffix = suffix or uuid4().hex[:8]
    supplier = Supplier(name=f"Receiving supplier {suffix}")
    location = Location(name=f"Receiving location {suffix}", type="warehouse", is_active=True)
    category = Category(name=f"Receiving category {suffix}", parent_id=None)
    db.add_all([supplier, location, category])
    db.flush()
    product = Product(
        sku=f"REC-{suffix}",
        name=f"Receiving product {suffix}",
        category_id=category.id,
        brand="Test",
        price=Decimal("100.00"),
        is_active=True,
        tracking_mode=tracking_mode,
    )
    db.add(product)
    db.flush()
    order = PurchaseOrder(
        po_number=f"PO-{suffix}",
        supplier_id=supplier.id,
        location_id=location.id,
        status="submitted",
        created_by=creator.id,
    )
    db.add(order)
    db.flush()
    line = PurchaseOrderLine(
        purchase_order_id=order.id,
        product_id=product.id,
        quantity_ordered=ordered,
        quantity_received=0,
        unit_price=Decimal("10.00"),
    )
    db.add(line)
    db.commit()
    return order, line, product, location, supplier


def signed_in(client, make_user, role: str, *, location_id: int | None = None) -> User:
    username = f"receive_{role}_{uuid4().hex[:6]}"
    user = make_user(username, role=role, location_id=location_id)
    assert login(client, username).status_code == 200
    return user


def receipt_line(
    line: PurchaseOrderLine,
    *,
    accepted: int = 0,
    damaged: int = 0,
    short: int = 0,
    **fields,
) -> dict:
    return {
        "po_line_id": line.id,
        "quantity_accepted": accepted,
        "quantity_damaged": damaged,
        "quantity_short": short,
        **fields,
    }


def test_full_receipt_updates_stock_cost_history_audit_and_status_notifications(
    client, make_user, db
):
    manager = make_user("full_receipt_manager", role="manager")
    order, line, product, location, supplier = create_order(db, manager)
    signed_in(client, make_user, "manager")

    response = client.post(
        f"/api/purchasing/purchase-orders/{order.id}/receive",
        json={"lines": [receipt_line(line, accepted=50, unit_price="12.50")]},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "received"
    assert response.json()["lines"][0]["quantity_received"] == 50
    assert response.json()["lines"][0]["quantity_outstanding"] == 0
    assert (
        db.scalar(
            select(StockLevel.quantity).where(
                StockLevel.product_id == product.id,
                StockLevel.location_id == location.id,
            )
        )
        == 50
    )
    average_cost = db.scalar(select(ItemCost.average_cost).where(ItemCost.product_id == product.id))
    assert average_cost == Decimal("12.5000")
    price_history = db.scalars(
        select(SupplierPriceHistory).where(SupplierPriceHistory.supplier_id == supplier.id)
    ).all()
    assert len(price_history) == 1
    assert price_history[0].unit_price == Decimal("12.50")
    receipt = db.scalar(
        select(PurchaseOrderReceipt).where(PurchaseOrderReceipt.purchase_order_id == order.id)
    )
    receipt_line_row = db.scalar(
        select(PurchaseOrderReceiptLine).where(PurchaseOrderReceiptLine.receipt_id == receipt.id)
    )
    movement = db.scalar(
        select(StockMovement).where(
            StockMovement.reference_type == "po_receipt_line",
            StockMovement.reference_id == receipt_line_row.id,
        )
    )
    assert movement.quantity_change == 50
    assert movement.location_id == location.id
    assert db.scalar(
        select(AuditLog.id).where(
            AuditLog.entity_type == "purchase_order",
            AuditLog.entity_id == str(order.id),
            AuditLog.action == "purchase_order_receipt_recorded",
        )
    )
    assert (
        db.scalar(
            select(Notification.message).where(
                Notification.recipient_user_id == manager.id,
                Notification.reference_id == order.id,
            )
        )
        == f"{order.po_number}: Received"
    )


def test_multiple_receipts_accumulate_and_short_items_remain_outstanding(client, make_user, db):
    manager = signed_in(client, make_user, "manager")
    order, line, product, location, _supplier = create_order(db, manager, ordered=200)

    first = client.post(
        f"/api/purchasing/purchase-orders/{order.id}/receive",
        json={"lines": [receipt_line(line, accepted=75)]},
    )
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "partially_received"
    assert first.json()["lines"][0]["quantity_outstanding"] == 125

    second = client.post(
        f"/api/purchasing/purchase-orders/{order.id}/receive",
        json={"lines": [receipt_line(line, accepted=125)]},
    )
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "received"
    assert second.json()["lines"][0]["quantity_received"] == 200
    assert (
        db.scalar(
            select(StockLevel.quantity).where(
                StockLevel.product_id == product.id,
                StockLevel.location_id == location.id,
            )
        )
        == 200
    )

    partial_order, partial_line, partial_product, partial_location, _ = create_order(
        db, manager, ordered=20
    )
    discrepancy = client.post(
        f"/api/purchasing/purchase-orders/{partial_order.id}/receive",
        json={
            "lines": [
                receipt_line(
                    partial_line,
                    accepted=15,
                    damaged=2,
                    short=3,
                    discrepancy_note="Two damaged; three units short.",
                )
            ]
        },
    )
    assert discrepancy.status_code == 200, discrepancy.text
    assert discrepancy.json()["status"] == "partially_received"
    assert discrepancy.json()["lines"][0]["quantity_received"] == 17
    assert discrepancy.json()["lines"][0]["quantity_outstanding"] == 3
    assert (
        db.scalar(
            select(StockLevel.quantity).where(
                StockLevel.product_id == partial_product.id,
                StockLevel.location_id == partial_location.id,
            )
        )
        == 15
    )
    saved_discrepancy = db.scalar(
        select(PurchaseOrderReceiptLine).where(
            PurchaseOrderReceiptLine.po_line_id == partial_line.id
        )
    )
    assert saved_discrepancy.quantity_damaged == 2
    assert saved_discrepancy.quantity_short == 3
    assert saved_discrepancy.discrepancy_note == "Two damaged; three units short."


def test_over_receipt_rejects_without_creating_any_receipt_or_stock_changes(client, make_user, db):
    manager = signed_in(client, make_user, "manager")
    order, line, product, location, supplier = create_order(db, manager, ordered=5)

    response = client.post(
        f"/api/purchasing/purchase-orders/{order.id}/receive",
        json={"lines": [receipt_line(line, accepted=6)]},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Received quantity exceeds outstanding order quantity"
    assert (
        db.scalar(
            select(PurchaseOrderReceipt.id).where(
                PurchaseOrderReceipt.purchase_order_id == order.id
            )
        )
        is None
    )
    assert (
        db.scalar(
            select(StockLevel.id).where(
                StockLevel.product_id == product.id,
                StockLevel.location_id == location.id,
            )
        )
        is None
    )
    assert (
        db.scalar(
            select(SupplierPriceHistory.id).where(SupplierPriceHistory.supplier_id == supplier.id)
        )
        is None
    )
    assert db.get(PurchaseOrder, order.id).status == "submitted"


def test_receipt_recalculates_weighted_average_using_accepted_stock(client, make_user, db):
    manager = signed_in(client, make_user, "manager")
    order, line, product, location, _supplier = create_order(db, manager, ordered=10)
    db.add(
        StockLevel(
            product_id=product.id,
            variant_id=None,
            location_id=location.id,
            quantity=10,
        )
    )
    db.add(ItemCost(product_id=product.id, variant_id=None, average_cost=Decimal("5.0000")))
    db.commit()

    response = client.post(
        f"/api/purchasing/purchase-orders/{order.id}/receive",
        json={"lines": [receipt_line(line, accepted=10, unit_price="15.00")]},
    )

    assert response.status_code == 200, response.text
    average_cost = db.scalar(select(ItemCost.average_cost).where(ItemCost.product_id == product.id))
    assert average_cost == Decimal("10.0000")
    assert (
        db.scalar(
            select(StockLevel.quantity).where(
                StockLevel.product_id == product.id,
                StockLevel.location_id == location.id,
            )
        )
        == 20
    )


def test_receipt_integrates_batch_and_serial_tracking(client, make_user, db):
    manager = signed_in(client, make_user, "manager")
    batch_order, batch_line, batch_product, location, _ = create_order(
        db, manager, ordered=2, tracking_mode="batch"
    )
    batch_response = client.post(
        f"/api/purchasing/purchase-orders/{batch_order.id}/receive",
        json={"lines": [receipt_line(batch_line, accepted=2, batch_number="LOT-22")]},
    )
    assert batch_response.status_code == 200, batch_response.text
    batch = db.scalar(select(Batch).where(Batch.product_id == batch_product.id))
    assert batch is not None
    assert (
        db.scalar(select(BatchStock.quantity_on_hand).where(BatchStock.batch_id == batch.id)) == 2
    )
    assert db.scalar(select(BatchReceipt.quantity).where(BatchReceipt.batch_id == batch.id)) == 2

    serial_order, serial_line, serial_product, serial_location, _ = create_order(
        db, manager, ordered=3, tracking_mode="serial"
    )
    serial_response = client.post(
        f"/api/purchasing/purchase-orders/{serial_order.id}/receive",
        json={
            "lines": [
                receipt_line(
                    serial_line,
                    accepted=2,
                    damaged=1,
                    discrepancy_note="One screen cracked.",
                    serial_numbers=["SN-ACCEPT-1", "SN-ACCEPT-2"],
                    damaged_serial_numbers=["SN-DAMAGED-1"],
                )
            ]
        },
    )
    assert serial_response.status_code == 200, serial_response.text
    serial_rows = db.scalars(
        select(SerialNumber).where(SerialNumber.product_id == serial_product.id)
    ).all()
    assert {row.serial_number: row.status for row in serial_rows} == {
        "SN-ACCEPT-1": "in_stock",
        "SN-ACCEPT-2": "in_stock",
        "SN-DAMAGED-1": "damaged",
    }
    assert (
        db.scalar(
            select(StockLevel.quantity).where(
                StockLevel.product_id == serial_product.id,
                StockLevel.location_id == serial_location.id,
            )
        )
        == 2
    )
    assert db.scalar(
        select(PurchaseOrderReceiptSerial.receipt_line_id).where(
            PurchaseOrderReceiptSerial.serial_number_id
            == db.scalar(
                select(SerialNumber.id).where(SerialNumber.serial_number == "SN-DAMAGED-1")
            )
        )
    )


def test_duplicate_serial_rolls_back_receipt_and_stock(client, make_user, db):
    manager = signed_in(client, make_user, "manager")
    order, line, product, location, _ = create_order(db, manager, ordered=1, tracking_mode="serial")
    db.add(
        SerialNumber(
            serial_number="SN-EXISTS",
            product_id=product.id,
            location_id=location.id,
            status="sold",
        )
    )
    db.commit()

    response = client.post(
        f"/api/purchasing/purchase-orders/{order.id}/receive",
        json={"lines": [receipt_line(line, accepted=1, serial_numbers=["SN-EXISTS"])]},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Duplicate serial number"
    assert (
        db.scalar(
            select(PurchaseOrderReceipt.id).where(
                PurchaseOrderReceipt.purchase_order_id == order.id
            )
        )
        is None
    )
    assert (
        db.scalar(
            select(StockLevel.id).where(
                StockLevel.product_id == product.id,
                StockLevel.location_id == location.id,
            )
        )
        is None
    )
    assert db.get(PurchaseOrderLine, line.id).quantity_received == 0


def test_staff_can_receive_only_assigned_location_orders_and_cashier_is_denied(
    client, make_user, db
):
    creator = make_user("receiving_creator", role="manager")
    order, line, _product, location, _supplier = create_order(db, creator, ordered=2)
    staff = signed_in(client, make_user, "staff", location_id=location.id)

    receivable = client.get("/api/purchasing/purchase-orders/receivable")
    assert receivable.status_code == 200
    assert [row["id"] for row in receivable.json()] == [order.id]
    accepted = client.post(
        f"/api/purchasing/purchase-orders/{order.id}/receive",
        json={"lines": [receipt_line(line, accepted=1)]},
    )
    assert accepted.status_code == 200, accepted.text

    other_order, other_line, other_product, other_location, _ = create_order(db, creator, ordered=1)
    forbidden = client.post(
        f"/api/purchasing/purchase-orders/{other_order.id}/receive",
        json={"lines": [receipt_line(other_line, accepted=1)]},
    )
    assert forbidden.status_code == 403
    assert (
        db.scalar(
            select(PurchaseOrderReceipt.id).where(
                PurchaseOrderReceipt.purchase_order_id == other_order.id
            )
        )
        is None
    )
    assert (
        db.scalar(
            select(StockLevel.id).where(
                StockLevel.product_id == other_product.id,
                StockLevel.location_id == other_location.id,
            )
        )
        is None
    )
    assert staff.location_id == location.id

    client.post("/api/auth/logout")
    signed_in(client, make_user, "cashier", location_id=location.id)
    assert client.get("/api/purchasing/purchase-orders/receivable").status_code == 403
    assert (
        client.post(
            f"/api/purchasing/purchase-orders/{other_order.id}/receive",
            json={"lines": [receipt_line(other_line, accepted=1)]},
        ).status_code
        == 403
    )


def test_concurrent_receipts_cannot_exceed_the_outstanding_order_quantity(empty_db_url: URL):
    command.upgrade(alembic_config(empty_db_url), "head")
    engine = create_engine(empty_db_url, pool_size=4)
    try:
        with Session(engine) as setup:
            supplier = Supplier(name="Concurrent Receipt Supplier")
            location = Location(name="Concurrent Receipt Location", type="warehouse")
            category = Category(name="Concurrent Receipt Category")
            setup.add_all([supplier, location, category])
            setup.flush()
            product = Product(
                sku="CONCURRENT-RECEIPT",
                name="Concurrent Receipt Product",
                category_id=category.id,
                brand="Test",
                price=Decimal("20.00"),
            )
            user = User(
                username="concurrent_receipt_manager",
                full_name="Concurrent Receipt Manager",
                password_hash="not-used-in-service-test",
                role="manager",
            )
            setup.add_all([product, user])
            setup.flush()
            order = PurchaseOrder(
                po_number="PO-CONCURRENT-RECEIPT",
                supplier_id=supplier.id,
                location_id=location.id,
                status="submitted",
                created_by=user.id,
            )
            setup.add(order)
            setup.flush()
            line = PurchaseOrderLine(
                purchase_order_id=order.id,
                product_id=product.id,
                quantity_ordered=5,
                unit_price=Decimal("10.00"),
            )
            setup.add(line)
            setup.commit()
            order_id = order.id
            line_id = line.id
            product_id = product.id
            location_id = location.id
            actor = CurrentUser(
                id=user.id,
                username=user.username,
                full_name=user.full_name,
                role="manager",
                location_id=None,
            )

        barrier = Barrier(2)

        def receive() -> int:
            with Session(engine) as session:
                session.execute(text("SET lock_timeout = '10s'"))
                barrier.wait(timeout=10)
                try:
                    receive_purchase_order(
                        order_id,
                        PurchaseOrderReceiptInput(
                            lines=[
                                PurchaseOrderReceiptLineInput(
                                    po_line_id=line_id,
                                    quantity_accepted=4,
                                )
                            ]
                        ),
                        session,
                        actor,
                    )
                    return 200
                except HTTPException as exc:
                    session.rollback()
                    return exc.status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(receive) for _ in range(2)]
            results = [future.result(timeout=15) for future in futures]
        assert sorted(results) == [200, 409]

        with Session(engine) as verify:
            assert (
                verify.scalar(
                    select(PurchaseOrderLine.quantity_received).where(
                        PurchaseOrderLine.id == line_id
                    )
                )
                == 4
            )
            assert (
                verify.scalar(
                    select(StockLevel.quantity).where(
                        StockLevel.product_id == product_id,
                        StockLevel.location_id == location_id,
                    )
                )
                == 4
            )
            assert (
                verify.scalar(
                    select(func.count())
                    .select_from(PurchaseOrderReceipt)
                    .where(PurchaseOrderReceipt.purchase_order_id == order_id)
                )
                == 1
            )
    finally:
        engine.dispose()
