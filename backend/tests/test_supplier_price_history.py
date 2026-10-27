"""Supplier price history API tests for Issue #23."""

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth._internal.models import User
from app.modules.product._internal.models import Category, Product
from app.modules.purchasing._internal.models import (
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
    SupplierPriceHistory,
)
from app.modules.stock._internal.models import Location
from tests.helpers import login


def create_supplier_order(
    db: Session,
    creator: User,
    *,
    suffix: str | None = None,
) -> tuple[Supplier, Product, PurchaseOrder, PurchaseOrderLine]:
    suffix = suffix or uuid4().hex[:8]
    supplier = Supplier(name=f"History supplier {suffix}")
    location = Location(name=f"History location {suffix}", type="warehouse")
    category = Category(name=f"History category {suffix}", parent_id=None)
    db.add_all([supplier, location, category])
    db.flush()
    product = Product(
        sku=f"HIST-{suffix}",
        name=f"History product {suffix}",
        category_id=category.id,
        brand="Test",
        price=Decimal("30000.00"),
        is_active=True,
    )
    db.add(product)
    db.flush()
    order = PurchaseOrder(
        po_number=f"PO-HIST-{suffix}",
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
        quantity_ordered=2,
        quantity_received=0,
        unit_price=Decimal("25000.00"),
    )
    db.add(line)
    db.commit()
    return supplier, product, order, line


def test_receipts_append_price_history_and_filters_keep_supplier_attribution(client, make_user, db):
    username = f"history_manager_{uuid4().hex[:6]}"
    manager = make_user(username, role="manager")
    assert login(client, username).status_code == 200
    supplier, product, order, line = create_supplier_order(db, manager)

    first = client.post(
        f"/api/purchasing/purchase-orders/{order.id}/receive",
        json={
            "lines": [
                {
                    "po_line_id": line.id,
                    "quantity_accepted": 1,
                    "unit_price": "25000.00",
                }
            ]
        },
    )
    assert first.status_code == 200, first.text
    first_history = db.scalar(
        select(SupplierPriceHistory).where(SupplierPriceHistory.receipt_line_id.is_not(None))
    )
    assert first_history is not None
    assert first_history.supplier_id == supplier.id
    assert first_history.product_id == product.id
    assert first_history.unit_price == Decimal("25000.00")
    assert isinstance(first_history.recorded_at, datetime)
    first_id = first_history.id
    first_recorded_at = first_history.recorded_at

    second = client.post(
        f"/api/purchasing/purchase-orders/{order.id}/receive",
        json={
            "lines": [
                {
                    "po_line_id": line.id,
                    "quantity_accepted": 1,
                    "unit_price": "24000.00",
                }
            ]
        },
    )
    assert second.status_code == 200, second.text
    other_supplier = Supplier(name=f"Other history supplier {uuid4().hex[:8]}")
    other_location = Location(name=f"Other history location {uuid4().hex[:8]}", type="warehouse")
    db.add_all([other_supplier, other_location])
    db.flush()
    other_order = PurchaseOrder(
        po_number=f"PO-OTHER-HIST-{uuid4().hex[:8]}",
        supplier_id=other_supplier.id,
        location_id=other_location.id,
        status="submitted",
        created_by=manager.id,
    )
    db.add(other_order)
    db.flush()
    other_line = PurchaseOrderLine(
        purchase_order_id=other_order.id,
        product_id=product.id,
        quantity_ordered=1,
        quantity_received=0,
        unit_price=Decimal("26000.00"),
    )
    db.add(other_line)
    db.commit()
    other_receipt = client.post(
        f"/api/purchasing/purchase-orders/{other_order.id}/receive",
        json={
            "lines": [
                {
                    "po_line_id": other_line.id,
                    "quantity_accepted": 1,
                    "unit_price": "26000.00",
                }
            ]
        },
    )
    assert other_receipt.status_code == 200, other_receipt.text

    rows = client.get("/api/purchasing/suppliers/price-history")
    assert rows.status_code == 200
    history = rows.json()
    assert [row["unit_price"] for row in history] == ["25000.00", "24000.00", "26000.00"]
    assert [row["id"] for row in history] == sorted(row["id"] for row in history)
    assert history[0]["id"] == first_id
    assert (
        datetime.fromisoformat(history[0]["recorded_at"].replace("Z", "+00:00"))
        == first_recorded_at
    )
    recorded_at = [
        datetime.fromisoformat(row["recorded_at"].replace("Z", "+00:00")) for row in history
    ]
    assert recorded_at == sorted(recorded_at)
    assert [row["supplier_id"] for row in history] == [
        supplier.id,
        supplier.id,
        other_supplier.id,
    ]
    assert all(row["product_id"] == product.id for row in history)
    assert [row["supplier_name"] for row in history] == [
        supplier.name,
        supplier.name,
        other_supplier.name,
    ]
    assert all(row["product_name"] == product.name for row in history)

    supplier_filter = client.get(
        "/api/purchasing/suppliers/price-history", params={"supplier_id": supplier.id}
    )
    assert supplier_filter.status_code == 200
    assert [row["unit_price"] for row in supplier_filter.json()] == ["25000.00", "24000.00"]
    product_filter = client.get(
        "/api/purchasing/suppliers/price-history", params={"product_id": product.id}
    )
    assert product_filter.status_code == 200
    assert [row["unit_price"] for row in product_filter.json()] == [
        "25000.00",
        "24000.00",
        "26000.00",
    ]
    combined_filter = client.get(
        "/api/purchasing/suppliers/price-history",
        params={"supplier_id": supplier.id, "product_id": product.id},
    )
    assert combined_filter.status_code == 200
    assert [row["id"] for row in combined_filter.json()] == [row["id"] for row in history[:2]]

    unchanged = db.get(SupplierPriceHistory, first_id)
    assert unchanged is not None
    assert unchanged.unit_price == Decimal("25000.00")
    assert unchanged.recorded_at == first_recorded_at


def test_supplier_price_history_is_read_only_and_manager_admin_only(client, make_user, db):
    manager_username = f"history_manager_{uuid4().hex[:6]}"
    make_user(manager_username, role="manager")
    assert login(client, manager_username).status_code == 200
    assert client.post("/api/purchasing/suppliers/price-history").status_code == 405
    assert client.patch("/api/purchasing/suppliers/price-history").status_code in {404, 405, 422}
    assert client.delete("/api/purchasing/suppliers/price-history").status_code in {404, 405, 422}

    client.post("/api/auth/logout")
    admin_username = f"history_admin_{uuid4().hex[:6]}"
    make_user(admin_username, role="admin")
    assert login(client, admin_username).status_code == 200
    assert client.get("/api/purchasing/suppliers/price-history").status_code == 200

    for role in ("staff", "cashier"):
        client.post("/api/auth/logout")
        username = f"history_{role}_{uuid4().hex[:6]}"
        make_user(username, role=role, location_id=1)
        assert login(client, username).status_code == 200
        assert client.get("/api/purchasing/suppliers/price-history").status_code == 403
