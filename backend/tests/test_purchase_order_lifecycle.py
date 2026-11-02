"""End-to-end purchase order flows: create, submit, receive, notify (FR-3.2..3.4, FR-8.2)."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth._internal.models import User
from app.modules.product._internal.models import Category, Product
from app.modules.purchasing._internal.models import (
    Supplier,
    SupplierPriceHistory,
    SupplierProduct,
)
from app.modules.stock._internal.models import Location, StockLevel
from tests.helpers import login


def _sign_in(client, make_user, role: str, location: Location | None = None) -> User:
    username = f"lifecycle_{role}_{uuid4().hex[:6]}"
    user = make_user(username, role=role, location_id=location.id if location else None)
    assert login(client, username).status_code == 200
    return user


def _catalog(db: Session, products: int = 1, suppliers: int = 1):
    """Suppliers that each list every product, a warehouse, and the products."""
    suffix = uuid4().hex[:8]
    category = Category(name=f"Lifecycle category {suffix}")
    location = Location(name=f"Warehouse-Bengaluru {suffix}", type="warehouse")
    supplier_rows = [Supplier(name=f"Supplier {index} {suffix}") for index in range(suppliers)]
    db.add_all([category, location, *supplier_rows])
    db.flush()
    product_rows = [
        Product(
            sku=f"SKU-EL-{index}-{suffix}",
            name=f"Lifecycle product {index} {suffix}",
            category_id=category.id,
            brand="Test",
            price=Decimal("30000.00"),
        )
        for index in range(products)
    ]
    db.add_all(product_rows)
    db.flush()
    db.add_all(
        SupplierProduct(
            supplier_id=supplier.id,
            product_id=product.id,
            supplier_price=Decimal("25000.00"),
        )
        for supplier in supplier_rows
        for product in product_rows
    )
    db.commit()
    return supplier_rows, location, product_rows


def _create_po(client, supplier: Supplier, location: Location, lines: list[tuple[Product, int]]):
    response = client.post(
        "/api/purchasing/purchase-orders",
        json={
            "supplier_id": supplier.id,
            "location_id": location.id,
            "expected_delivery_date": (date.today() + timedelta(days=7)).isoformat(),
            "lines": [
                {"product_id": product.id, "quantity_ordered": quantity, "unit_price": "24500.00"}
                for product, quantity in lines
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _receive(client, order: dict, quantities: dict[int, int]):
    return client.post(
        f"/api/purchasing/purchase-orders/{order['id']}/receive",
        json={
            "lines": [
                {"po_line_id": line["id"], "quantity_accepted": quantities[line["product_id"]]}
                for line in order["lines"]
                if quantities.get(line["product_id"])
            ]
        },
    )


def _stock(db: Session, product: Product, location: Location) -> int | None:
    return db.scalar(
        select(StockLevel.quantity).where(
            StockLevel.product_id == product.id, StockLevel.location_id == location.id
        )
    )


def test_fr3_2_st_1_three_line_po_goes_from_creation_to_received_with_stock(client, make_user, db):
    [supplier], location, products = _catalog(db, products=3)
    _sign_in(client, make_user, "manager")

    order = _create_po(
        client, supplier, location, [(products[0], 5), (products[1], 10), (products[2], 2)]
    )
    assert order["status"] == "draft"
    assert Decimal(order["total"]) == Decimal("24500.00") * 17
    submitted = client.post(f"/api/purchasing/purchase-orders/{order['id']}/submit")
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "submitted"

    received = _receive(client, order, {products[0].id: 5, products[1].id: 10, products[2].id: 2})

    assert received.status_code == 200, received.text
    assert received.json()["status"] == "received"
    assert [_stock(db, product, location) for product in products] == [5, 10, 2]
    assert client.get(f"/api/purchasing/purchase-orders/{order['id']}").json()["status"] == (
        "received"
    )


def test_fr3_3_it_1_receipt_adds_stock_only_at_the_po_receiving_location(client, make_user, db):
    [supplier], warehouse, [product] = _catalog(db)
    store = Location(name=f"Store-Chennai {uuid4().hex[:6]}", type="store")
    db.add(store)
    db.add(StockLevel(product_id=product.id, location_id=store.id, quantity=7))
    db.commit()
    _sign_in(client, make_user, "manager")
    order = _create_po(client, supplier, warehouse, [(product, 12)])
    assert client.post(f"/api/purchasing/purchase-orders/{order['id']}/submit").status_code == 200

    assert _receive(client, order, {product.id: 12}).status_code == 200

    assert _stock(db, product, warehouse) == 12
    assert _stock(db, product, store) == 7


def test_fr3_3_st_1_staff_finish_a_po_over_two_sessions(client, make_user, db):
    [supplier], location, [product] = _catalog(db)
    _sign_in(client, make_user, "manager")
    order = _create_po(client, supplier, location, [(product, 200)])
    assert client.post(f"/api/purchasing/purchase-orders/{order['id']}/submit").status_code == 200
    client.post("/api/auth/logout")

    staff = _sign_in(client, make_user, "staff", location)
    first = _receive(client, order, {product.id: 120})
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "partially_received"
    assert first.json()["lines"][0]["quantity_outstanding"] == 80
    client.post("/api/auth/logout")

    assert login(client, staff.username).status_code == 200
    second = _receive(client, order, {product.id: 80})

    assert second.status_code == 200, second.text
    assert second.json()["status"] == "received"
    assert second.json()["lines"][0]["quantity_received"] == 200
    assert _stock(db, product, location) == 200


def test_fr3_4_st_1_manager_compares_supplier_prices_then_orders_from_the_cheaper(
    client, make_user, db
):
    (tech, global_supply), location, [product] = _catalog(db, suppliers=2)
    db.add_all(
        [
            SupplierPriceHistory(
                supplier_id=tech.id, product_id=product.id, unit_price=Decimal("25000.00")
            ),
            SupplierPriceHistory(
                supplier_id=global_supply.id, product_id=product.id, unit_price=Decimal("24500.00")
            ),
        ]
    )
    db.commit()
    _sign_in(client, make_user, "manager")

    history = client.get(
        "/api/purchasing/suppliers/price-history", params={"product_id": product.id}
    )
    assert history.status_code == 200
    latest = {row["supplier_id"]: Decimal(row["unit_price"]) for row in history.json()}
    assert latest == {tech.id: Decimal("25000.00"), global_supply.id: Decimal("24500.00")}
    cheapest = min(latest, key=latest.__getitem__)
    chosen = tech if cheapest == tech.id else global_supply

    order = _create_po(client, chosen, location, [(product, 4)])

    assert order["supplier_id"] == global_supply.id
    assert order["supplier_name"] == global_supply.name
    assert order["lines"][0]["unit_price"] == "24500.00"
    assert order["total"] == "98000.00"


def _messages(client) -> list[str]:
    response = client.get("/api/notifications", params={"limit": 50})
    assert response.status_code == 200, response.text
    return [row["message"] for row in response.json() if row["type"] == "po_status"]


def test_fr8_2_st_1_manager_sees_the_full_po_notification_trail(client, make_user, db):
    [supplier], location, [product] = _catalog(db)
    manager = _sign_in(client, make_user, "manager")
    order = _create_po(client, supplier, location, [(product, 10)])
    number = order["po_number"]

    assert client.post(f"/api/purchasing/purchase-orders/{order['id']}/submit").status_code == 200
    assert _receive(client, order, {product.id: 4}).status_code == 200
    assert _receive(client, order, {product.id: 6}).status_code == 200

    client.post("/api/auth/logout")
    assert login(client, manager.username).status_code == 200
    trail = [message for message in _messages(client) if message.startswith(number)]
    # Newest first, as the panel shows them.
    assert trail == [f"{number}: Received", f"{number}: Partially Received", f"{number}: Submitted"]


def test_fr8_2_it_3_status_changes_across_pos_are_listed_in_event_order(client, make_user, db):
    [supplier], location, [product] = _catalog(db)
    _sign_in(client, make_user, "manager")
    first = _create_po(client, supplier, location, [(product, 1)])
    second = _create_po(client, supplier, location, [(product, 1)])
    third = _create_po(client, supplier, location, [(product, 1)])

    assert client.post(f"/api/purchasing/purchase-orders/{first['id']}/submit").status_code == 200
    assert client.post(f"/api/purchasing/purchase-orders/{second['id']}/submit").status_code == 200
    assert client.post(f"/api/purchasing/purchase-orders/{third['id']}/cancel").status_code == 200

    rows = client.get("/api/notifications", params={"limit": 50}).json()
    po_rows = [row for row in rows if row["type"] == "po_status"]
    assert [row["message"] for row in po_rows] == [
        f"{third['po_number']}: Cancelled",
        f"{second['po_number']}: Submitted",
        f"{first['po_number']}: Submitted",
    ]
    stamps = [datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")) for row in po_rows]
    assert stamps == sorted(stamps, reverse=True)
    assert all(stamp <= datetime.now(UTC) for stamp in stamps)


def test_fr8_2_st_2_po_status_notifications_are_not_shown_to_cashiers(client, make_user, db):
    [supplier], location, [product] = _catalog(db)
    _sign_in(client, make_user, "manager")
    order = _create_po(client, supplier, location, [(product, 1)])
    assert client.post(f"/api/purchasing/purchase-orders/{order['id']}/submit").status_code == 200
    client.post("/api/auth/logout")

    _sign_in(client, make_user, "cashier", location)

    assert client.get("/api/notifications").status_code == 403
    assert client.get("/api/notifications/unread-count").status_code in {403, 404}
