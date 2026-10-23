"""Per-location stock-level API and visibility (Issue #14)."""

from decimal import Decimal

from app.modules.product._internal.models import Category, Product, ProductVariant
from app.modules.stock._internal.models import Location, StockLevel
from tests.helpers import login


def test_stock_levels_are_per_location_and_expose_combined_totals(client, make_user, db):
    chennai = Location(name="Chennai", type="store")
    bengaluru = Location(name="Bengaluru", type="warehouse")
    phones = Category(name="Issue 14 Stock Phones")
    db.add_all([chennai, bengaluru, phones])
    db.flush()
    phone = Product(
        sku="PHONE-1",
        name="Test Phone",
        category_id=phones.id,
        brand="Test",
        price=Decimal("100"),
    )
    variant_phone = Product(
        sku="PHONE-2",
        name="Variant Phone",
        category_id=phones.id,
        brand="Test",
        price=Decimal("200"),
    )
    db.add_all([phone, variant_phone])
    db.flush()
    variant = ProductVariant(
        product_id=variant_phone.id,
        sku="PHONE-2-BLK",
        attributes={"color": "Black"},
    )
    db.add(variant)
    db.flush()
    db.add_all(
        [
            StockLevel(product_id=phone.id, location_id=chennai.id, quantity=50),
            StockLevel(product_id=phone.id, location_id=bengaluru.id, quantity=200),
            StockLevel(
                product_id=variant_phone.id,
                variant_id=variant.id,
                location_id=chennai.id,
                quantity=7,
            ),
            StockLevel(
                product_id=variant_phone.id,
                variant_id=variant.id,
                location_id=bengaluru.id,
                quantity=13,
            ),
        ]
    )
    db.commit()
    make_user("manager_stock_levels", role="manager")
    assert login(client, "manager_stock_levels").status_code == 200

    response = client.get("/api/stock/levels")
    assert response.status_code == 200, response.text
    test_product_ids = {phone.id, variant_phone.id}
    levels = [row for row in response.json() if row["product_id"] in test_product_ids]
    assert len(levels) == 4
    base_product = [row for row in levels if row["variant_id"] is None]
    variant_product = [row for row in levels if row["variant_id"] == variant.id]
    assert {(row["location_name"], row["quantity"]) for row in base_product} == {
        ("Chennai", 50),
        ("Bengaluru", 200),
    }
    assert {row["total_quantity"] for row in base_product} == {250}
    assert {(row["location_name"], row["quantity"]) for row in variant_product} == {
        ("Chennai", 7),
        ("Bengaluru", 13),
    }
    assert {row["total_quantity"] for row in variant_product} == {20}

    filtered = client.get(f"/api/stock/levels?location_id={chennai.id}")
    assert filtered.status_code == 200
    filtered_levels = [row for row in filtered.json() if row["product_id"] in test_product_ids]
    assert {row["location_name"] for row in filtered_levels} == {"Chennai"}
    assert {row["total_quantity"] for row in filtered_levels if row["variant_id"] is None} == {250}


def test_staff_stock_levels_are_scoped_to_assigned_location(client, make_user, db):
    assigned = Location(name="Assigned Store", type="store")
    other = Location(name="Other Store", type="store")
    category = Category(name="Issue 14 Stock Accessories")
    db.add_all([assigned, other, category])
    db.flush()
    product = Product(
        sku="CABLE-1",
        name="Test Cable",
        category_id=category.id,
        brand="Test",
        price=Decimal("10"),
    )
    db.add(product)
    db.flush()
    db.add_all(
        [
            StockLevel(product_id=product.id, location_id=assigned.id, quantity=4),
            StockLevel(product_id=product.id, location_id=other.id, quantity=8),
        ]
    )
    db.commit()
    make_user("stock_staff", role="staff", location_id=assigned.id)
    assert login(client, "stock_staff").status_code == 200

    response = client.get("/api/stock/levels")
    assert response.status_code == 200, response.text
    assert response.json() == [
        {
            "product_id": product.id,
            "product_name": "Test Cable",
            "sku": "CABLE-1",
            "category_id": category.id,
            "category_name": "Issue 14 Stock Accessories",
            "variant_id": None,
            "variant_sku": None,
            "variant_attributes": None,
            "location_id": assigned.id,
            "location_name": "Assigned Store",
            "quantity": 4,
            "total_quantity": 4,
        }
    ]
    forbidden = client.get(f"/api/stock/levels?location_id={other.id}")
    assert forbidden.status_code == 403
