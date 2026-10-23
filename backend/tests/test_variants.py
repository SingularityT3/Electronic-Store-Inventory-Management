from decimal import Decimal

from app.modules.audit import AuditFilter, audit_service
from app.modules.product._internal.models import (
    Category,
    CategoryAttribute,
    Product,
    ProductVariant,
)
from app.modules.stock._internal.models import Location, StockLevel
from tests.helpers import login


def product_payload(category_id: int, **overrides):
    return {
        "name": "Galaxy A54",
        "sku": "GAL-A54",
        "category_id": category_id,
        "brand": "Samsung",
        "price": "28999.00",
        **overrides,
    }


def category_with_attributes(db, name):
    category = Category(name=name)
    db.add(category)
    db.flush()
    db.add_all(
        [
            CategoryAttribute(
                category_id=category.id,
                name="Color",
                position=0,
                allowed_values=["Black", "White"],
            ),
            CategoryAttribute(
                category_id=category.id,
                name="Storage",
                position=1,
                allowed_values=["128GB", "256GB"],
            ),
        ]
    )
    db.commit()
    return category


def variant_payload(sku="GAL-A54-BLK-128", **overrides):
    return {
        "sku": sku,
        "attributes": {"Color": "Black", "Storage": "128GB"},
        "price": None,
        **overrides,
    }


def create_product(client, category_id, **overrides):
    return client.post("/api/product", json=product_payload(category_id, **overrides)).json()


def test_variants_normalize_attributes_and_use_effective_price(client, db, make_user):
    manager = make_user("variant_manager_one")
    category = category_with_attributes(db, "Mobile Phones One")
    login(client, manager.username)
    product = create_product(client, category.id)

    created = client.post(
        f"/api/product/{product['id']}/variants",
        json=variant_payload(attributes={"storage": "128gb", "color": "black"}),
    )

    assert created.status_code == 201
    assert created.json()["attributes"] == {"Color": "Black", "Storage": "128GB"}
    assert Decimal(created.json()["effective_price"]) == Decimal("28999.00")
    assert client.get(f"/api/product/{product['id']}/variants").json()[0]["stock"] == 0


def test_duplicate_variant_combination_and_sku_are_field_errors(client, db, make_user):
    manager = make_user("variant_manager_two")
    category = category_with_attributes(db, "Mobile Phones Two")
    login(client, manager.username)
    product = create_product(client, category.id)
    assert (
        client.post(f"/api/product/{product['id']}/variants", json=variant_payload()).status_code
        == 201
    )

    duplicate = client.post(
        f"/api/product/{product['id']}/variants",
        json=variant_payload("GAL-A54-BLK-256", attributes={"storage": "128gb", "color": "black"}),
    )
    duplicate_sku = client.post(
        f"/api/product/{product['id']}/variants",
        json=variant_payload("GAL-A54-BLK-128", attributes={"Color": "White", "Storage": "256GB"}),
    )

    assert duplicate.status_code == 422
    assert duplicate.json()["detail"]["message"] == "Variant combination already exists"
    assert duplicate_sku.status_code == 422
    assert duplicate_sku.json()["detail"]["message"] == "SKU already exists"
    assert db.query(ProductVariant).filter(ProductVariant.product_id == product["id"]).count() == 1


def test_variant_stock_is_independent_and_delete_is_soft(client, db, make_user):
    manager = make_user("variant_manager_three")
    category = category_with_attributes(db, "Mobile Phones Three")
    location = Location(name="Variant Test Store", type="store")
    db.add(location)
    db.commit()
    login(client, manager.username)
    product = create_product(client, category.id)
    black = client.post(f"/api/product/{product['id']}/variants", json=variant_payload()).json()
    white = client.post(
        f"/api/product/{product['id']}/variants",
        json=variant_payload("GAL-A54-WHT-256", attributes={"Color": "White", "Storage": "256GB"}),
    ).json()
    db.add_all(
        [
            StockLevel(
                product_id=product["id"],
                variant_id=black["id"],
                location_id=location.id,
                quantity=10,
            ),
            StockLevel(
                product_id=product["id"],
                variant_id=white["id"],
                location_id=location.id,
                quantity=5,
            ),
        ]
    )
    db.commit()

    listed = client.get(f"/api/product/{product['id']}/variants").json()
    assert {item["id"]: item["stock"] for item in listed} == {black["id"]: 10, white["id"]: 5}
    blocked = client.delete(f"/api/product/{product['id']}/variants/{black['id']}")
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "Cannot delete variant with existing stock"

    db.query(StockLevel).filter(StockLevel.variant_id == white["id"]).delete()
    db.commit()
    assert client.delete(f"/api/product/{product['id']}/variants/{white['id']}").status_code == 204
    assert [item["id"] for item in client.get(f"/api/product/{product['id']}/variants").json()] == [
        black["id"]
    ]
    assert db.get(Product, product["id"]).is_active
    assert (
        audit_service.list_entries(
            db, AuditFilter(action="variant_deleted"), limit=10, offset=0
        ).total
        == 1
    )
