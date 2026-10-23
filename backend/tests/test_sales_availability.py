"""Point-of-sale stock availability is location-scoped."""

from decimal import Decimal

from app.modules.product._internal.models import Category, Product
from app.modules.stock._internal.models import Location, StockLevel
from tests.helpers import login


def test_cashier_availability_uses_only_assigned_location(client, make_user, db):
    chennai = Location(name="POS Chennai", type="store")
    bengaluru = Location(name="POS Bengaluru", type="store")
    category = Category(name="POS Phones")
    db.add_all([chennai, bengaluru, category])
    db.flush()
    product = Product(
        sku="POS-PHONE",
        name="POS Phone",
        category_id=category.id,
        brand="Test",
        price=Decimal("100"),
    )
    db.add(product)
    db.flush()
    db.add_all(
        [
            StockLevel(product_id=product.id, location_id=chennai.id, quantity=70),
            StockLevel(product_id=product.id, location_id=bengaluru.id, quantity=180),
        ]
    )
    db.commit()
    make_user("pos_cashier", role="cashier", location_id=chennai.id)
    assert login(client, "pos_cashier").status_code == 200

    response = client.get("/api/sales/availability")
    assert response.status_code == 200, response.text
    assert response.json() == [
        {
            "product_id": product.id,
            "product_name": "POS Phone",
            "sku": "POS-PHONE",
            "variant_id": None,
            "variant_sku": None,
            "variant_attributes": None,
            "location_id": chennai.id,
            "location_name": "POS Chennai",
            "available_quantity": 70,
        }
    ]
    forbidden = client.get(f"/api/sales/availability?location_id={bengaluru.id}")
    assert forbidden.status_code == 403
    assert client.get("/api/stock/locations").status_code == 403


def test_manager_must_select_and_can_query_a_pos_location(client, make_user, db):
    location = Location(name="Manager POS Store", type="store")
    category = Category(name="Manager POS Category")
    db.add_all([location, category])
    db.flush()
    product = Product(
        sku="MANAGER-POS",
        name="Manager POS Product",
        category_id=category.id,
        brand="Test",
        price=Decimal("20"),
    )
    db.add(product)
    db.flush()
    db.add(StockLevel(product_id=product.id, location_id=location.id, quantity=3))
    db.commit()
    make_user("pos_manager", role="manager")
    assert login(client, "pos_manager").status_code == 200

    assert client.get("/api/sales/availability").status_code == 422
    response = client.get(f"/api/sales/availability?location_id={location.id}")
    assert response.status_code == 200, response.text
    assert response.json()[0]["available_quantity"] == 3
