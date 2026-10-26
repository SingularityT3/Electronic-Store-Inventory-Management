"""Which product items hold stock, and how stock screens treat items that change later."""

from decimal import Decimal

from app.modules.notifications._internal.models import StockAlert
from app.modules.product import product_stock_items
from app.modules.product._internal.models import Category, Product, ProductVariant
from app.modules.stock._internal.models import Location, StockLevel
from tests.helpers import login


def _setup(db):
    store = Location(name="Stock Items Store", type="store")
    category = Category(name="Stock Items Phones")
    db.add_all([store, category])
    db.flush()
    product = Product(
        sku="STOCK-ITEM-1",
        name="Stock Item Phone",
        category_id=category.id,
        brand="Test",
        price=Decimal("100"),
    )
    db.add(product)
    db.flush()
    return store, product


def _variant(db, product, sku="STOCK-ITEM-1-BLK", **fields):
    variant = ProductVariant(product_id=product.id, sku=sku, attributes={"color": sku}, **fields)
    db.add(variant)
    db.flush()
    return variant


def test_items_flag_what_can_hold_new_stock(db):
    _store, product = _setup(db)
    items = {(i.product_id, i.variant_id): i for i in product_stock_items(db, [product.id])}
    assert items[(product.id, None)].is_active

    deleted = _variant(db, product, "STOCK-ITEM-1-OLD", is_active=False)
    items = {(i.product_id, i.variant_id): i for i in product_stock_items(db, [product.id])}
    # Only deleted variants: the base product is stocked again.
    assert items[(product.id, None)].is_active
    assert not items[(product.id, deleted.id)].is_active

    active = _variant(db, product)
    items = {(i.product_id, i.variant_id): i for i in product_stock_items(db, [product.id])}
    assert not items[(product.id, None)].is_active
    assert items[(product.id, active.id)].is_active

    product.is_active = False
    db.flush()
    items = product_stock_items(db, [product.id])
    assert not any(item.is_active for item in items)


def test_stock_screens_survive_a_variant_added_after_base_stock_rows(client, make_user, db):
    store, product = _setup(db)
    # A zero base row remains after base stock ran out or a threshold was set.
    db.add(StockLevel(product_id=product.id, location_id=store.id, quantity=0))
    db.flush()
    _variant(db, product)
    db.commit()
    make_user("stock_items_manager", role="manager")
    assert login(client, "stock_items_manager").status_code == 200

    levels = client.get("/api/stock/levels")
    assert levels.status_code == 200, levels.text
    assert client.get(f"/api/sales/availability?location_id={store.id}").status_code == 200
    assert client.get("/api/reporting/valuation").status_code == 200


def test_new_stock_needs_an_active_item(client, make_user, db):
    store, product = _setup(db)
    variant = _variant(db, product)
    db.commit()
    make_user("stock_items_staff", role="staff", location_id=store.id)
    assert login(client, "stock_items_staff").status_code == 200

    def adjust(variant_id):
        return client.post(
            "/api/stock/adjustments",
            json={
                "product_id": product.id,
                "variant_id": variant_id,
                "location_id": store.id,
                "quantity_change": 5,
                "reason": "Found during count",
            },
        )

    # The base product of a product with variants holds no stock of its own.
    assert adjust(None).status_code == 404
    assert adjust(variant.id).status_code == 201

    product_two = Product(
        sku="STOCK-ITEM-2",
        name="Deleted Phone",
        category_id=product.category_id,
        brand="Test",
        price=Decimal("10"),
        is_active=False,
    )
    db.add(product_two)
    db.commit()
    response = client.post(
        "/api/stock/adjustments",
        json={
            "product_id": product_two.id,
            "location_id": store.id,
            "quantity_change": 5,
            "reason": "Found during count",
        },
    )
    assert response.status_code == 404


def test_variant_cannot_be_added_while_base_stock_remains(client, make_user, db):
    store, product = _setup(db)
    # A deleted variant used to skip the base-stock check.
    _variant(db, product, "STOCK-ITEM-1-OLD", is_active=False)
    db.add(StockLevel(product_id=product.id, location_id=store.id, quantity=3))
    db.commit()
    make_user("stock_items_variant_manager", role="manager")
    assert login(client, "stock_items_variant_manager").status_code == 200

    response = client.post(
        f"/api/product/{product.id}/variants",
        json={"sku": "STOCK-ITEM-1-NEW", "attributes": {"color": "Blue"}},
    )
    assert response.status_code == 409


def test_deleting_a_product_resolves_its_stock_alerts(client, make_user, db):
    store, product = _setup(db)
    db.add(StockLevel(product_id=product.id, location_id=store.id, quantity=0))
    db.add(
        StockAlert(
            product_id=product.id,
            location_id=store.id,
            product_name=product.name,
            sku=product.sku,
            location_name=store.name,
            alert_type="out_of_stock",
            quantity=0,
            threshold=2,
        )
    )
    db.commit()
    make_user("stock_items_alert_manager", role="manager")
    assert login(client, "stock_items_alert_manager").status_code == 200

    assert client.delete(f"/api/product/{product.id}").status_code == 204
    alerts = client.get(f"/api/notifications/alerts?location_id={store.id}").json()
    assert all(alert["product_id"] != product.id for alert in alerts)
    levels = client.get(f"/api/stock/levels?location_id={store.id}").json()
    assert all(level["product_id"] != product.id for level in levels)
