from decimal import Decimal

from app.modules.audit import AuditFilter, audit_service
from app.modules.product._internal.models import Category, Product
from app.modules.stock._internal.models import Location, StockLevel
from tests.helpers import login


def category(db):
    row = Category(name="Phones")
    db.add(row)
    db.commit()
    return row


def product_payload(category_id: int, **overrides):
    return {
        "name": "Phone",
        "sku": " PH-001 ",
        "category_id": category_id,
        "brand": "Acme",
        "price": "28999.00",
        "description": "A phone",
        **overrides,
    }


def test_manager_creates_and_lists_product(client, db, make_user):
    manager = make_user("manager")
    cat = category(db)
    login(client, manager.username)

    response = client.post("/api/product", json=product_payload(cat.id))

    assert response.status_code == 201
    assert response.json()["sku"] == "PH-001"
    listed = client.get("/api/product").json()
    assert [item["sku"] for item in listed["items"]] == ["PH-001"]


def test_product_validation_rejects_duplicate_blank_and_negative(client, db, make_user):
    manager = make_user("manager")
    cat = category(db)
    login(client, manager.username)
    assert client.post("/api/product", json=product_payload(cat.id)).status_code == 201

    duplicate = client.post("/api/product", json=product_payload(cat.id, sku=" ph-001 "))
    assert duplicate.status_code == 422
    assert duplicate.json()["detail"]["message"] == "SKU already exists"
    blank = client.post("/api/product", json=product_payload(cat.id, name="  "))
    assert blank.status_code == 422
    assert blank.json()["detail"]["message"] == "Product Name is required"
    negative = client.post("/api/product", json=product_payload(cat.id, price="-1"))
    assert negative.status_code == 422
    assert db.query(Product).count() == 1


def test_price_update_is_visible_to_cashier_and_audited(client, db, make_user):
    manager = make_user("manager")
    cashier = make_user("cashier", role="cashier", location_id=1)
    cat = category(db)
    login(client, manager.username)
    product = client.post("/api/product", json=product_payload(cat.id)).json()
    updated = client.put(
        f"/api/product/{product['id']}",
        json=product_payload(cat.id, price="26999.00"),
    )
    assert updated.status_code == 200

    login(client, cashier.username)
    assert Decimal(str(client.get(f"/api/product/{product['id']}").json()["price"])) == Decimal(
        "26999.00"
    )
    entries = audit_service.list_entries(
        db, AuditFilter(action="product_price_updated"), limit=10, offset=0
    )
    assert entries.entries[0].before == {"price": "28999.00"}
    assert entries.entries[0].after == {"price": "26999.00"}


def test_delete_requires_zero_stock_and_cashier_cannot_manage(client, db, make_user):
    manager = make_user("manager")
    cashier = make_user("cashier", role="cashier", location_id=1)
    cat = category(db)
    login(client, manager.username)
    product = client.post("/api/product", json=product_payload(cat.id)).json()
    location = db.get(Location, 1)
    if location is None:
        location = Location(name="Store", type="store")
        db.add(location)
        db.commit()
    db.add(StockLevel(product_id=product["id"], location_id=location.id, quantity=1))
    db.commit()
    blocked = client.delete(f"/api/product/{product['id']}")
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "Cannot delete product with existing stock"

    login(client, cashier.username)
    denied = client.post("/api/product", json=product_payload(cat.id, sku="PH-002"))
    assert denied.status_code == 403
