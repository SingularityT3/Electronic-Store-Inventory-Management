"""Product filters and sorting (FR-7.2, issue #13)."""

from decimal import Decimal
from uuid import uuid4

from app.modules.notifications._internal.models import StockAlert
from app.modules.product._internal.models import Category, Product
from app.modules.stock import update_stock
from app.modules.stock._internal.models import Location, StockLevel
from tests.helpers import login


def catalog(db):
    """Electronics > Mobile Phones > Smartphones, plus Laptops, with stock at two locations."""
    suffix = uuid4().hex[:8]
    electronics = Category(name=f"Filter Electronics {suffix}")
    db.add(electronics)
    db.flush()
    phones = Category(name="Mobile Phones", parent_id=electronics.id)
    laptops = Category(name="Laptops", parent_id=electronics.id)
    db.add_all([phones, laptops])
    db.flush()
    smartphones = Category(name="Smartphones", parent_id=phones.id)
    store = Location(name=f"Filter Store {suffix}", type="store")
    warehouse = Location(name=f"Filter Warehouse {suffix}", type="warehouse")
    db.add_all([smartphones, store, warehouse])
    db.flush()

    def product(name, category, price):
        item = Product(
            name=name,
            sku=f"FLT-{name}-{suffix}",
            category_id=category.id,
            brand="Test",
            price=Decimal(price),
        )
        db.add(item)
        db.flush()
        return item

    cheap_phone = product("Cheap Phone", smartphones, "8000")
    mid_phone = product("Mid Phone", phones, "20000")
    flagship = product("Flagship Phone", smartphones, "90000")
    laptop = product("Budget Laptop", laptops, "20000")
    db.add_all(
        [
            StockLevel(
                product_id=cheap_phone.id, location_id=store.id, quantity=3, reorder_threshold=5
            ),
            StockLevel(product_id=cheap_phone.id, location_id=warehouse.id, quantity=40),
            StockLevel(product_id=mid_phone.id, location_id=store.id, quantity=12),
            StockLevel(product_id=laptop.id, location_id=warehouse.id, quantity=7),
        ]
    )
    db.add(
        StockAlert(
            product_id=cheap_phone.id,
            location_id=store.id,
            product_name=cheap_phone.name,
            sku=cheap_phone.sku,
            location_name=store.name,
            alert_type="low_stock",
            quantity=3,
            threshold=5,
        )
    )
    db.commit()
    return {
        "electronics": electronics,
        "phones": phones,
        "store": store,
        "warehouse": warehouse,
        "cheap": cheap_phone,
        "mid": mid_phone,
        "flagship": flagship,
        "laptop": laptop,
    }


def names(response):
    assert response.status_code == 200, response.text
    return [item["name"] for item in response.json()["items"]]


def test_category_and_price_range_return_exactly_the_intersection(client, make_user, db):
    data = catalog(db)
    make_user("filter_manager", role="manager")
    assert login(client, "filter_manager").status_code == 200

    # Mobile Phones includes its Smartphones subcategory (FR7.2-IT-1).
    phones = client.get("/api/product", params={"category_id": data["phones"].id})
    assert names(phones) == ["Cheap Phone", "Flagship Phone", "Mid Phone"]
    in_range = client.get(
        "/api/product",
        params={"category_id": data["phones"].id, "min_price": "10000", "max_price": "50000"},
    )
    assert names(in_range) == ["Mid Phone"]
    assert in_range.json()["total"] == 1
    # Filters combine with search.
    searched = client.get(
        "/api/product",
        params={"q": "phone", "category_id": data["electronics"].id, "max_price": "20000"},
    )
    assert names(searched) == ["Cheap Phone", "Mid Phone"]

    bad_range = client.get("/api/product", params={"min_price": "10", "max_price": "5"})
    assert bad_range.status_code == 422


def test_price_and_stock_sorts_work_both_ways_on_live_data(client, make_user, db):
    data = catalog(db)
    make_user("sort_manager", role="manager")
    assert login(client, "sort_manager").status_code == 200
    scope = {"category_id": data["electronics"].id}

    by_price = client.get("/api/product", params={**scope, "sort": "price", "order": "desc"})
    assert names(by_price) == ["Flagship Phone", "Budget Laptop", "Mid Phone", "Cheap Phone"]

    # Totals across locations: cheap 43, mid 12, laptop 7, flagship 0 (FR7.2-UT-3).
    ascending = client.get("/api/product", params={**scope, "sort": "stock"})
    assert names(ascending) == ["Flagship Phone", "Budget Laptop", "Mid Phone", "Cheap Phone"]
    descending = client.get("/api/product", params={**scope, "sort": "stock", "order": "desc"})
    assert names(descending) == ["Cheap Phone", "Mid Phone", "Budget Laptop", "Flagship Phone"]

    paged = client.get(
        "/api/product", params={**scope, "sort": "stock", "page": 2, "page_size": 3}
    ).json()
    assert (paged["total"], [item["name"] for item in paged["items"]]) == (4, ["Cheap Phone"])

    # Sorting uses current stock: selling out the laptop moves it immediately.
    update_stock(
        db,
        product_id=data["laptop"].id,
        variant_id=None,
        location_id=data["warehouse"].id,
        quantity_delta=-7,
        movement_type="sale",
    )
    db.commit()
    out = client.get("/api/product", params={**scope, "stock_status": "out_of_stock"})
    assert names(out) == ["Budget Laptop", "Flagship Phone"]


def test_stock_status_filter_is_scoped_to_the_users_location(client, make_user, db):
    data = catalog(db)
    make_user("status_manager", role="manager")
    assert login(client, "status_manager").status_code == 200
    scope = {"category_id": data["electronics"].id}

    def status(value):
        return names(client.get("/api/product", params={**scope, "stock_status": value}))

    assert status("low_stock") == ["Cheap Phone"]
    assert status("in_stock") == ["Budget Laptop", "Mid Phone"]
    assert status("out_of_stock") == ["Flagship Phone"]

    make_user("status_staff", role="staff", location_id=data["warehouse"].id)
    assert login(client, "status_staff").status_code == 200
    # At the warehouse the cheap phone is healthy and the mid phone has none.
    assert status("low_stock") == []
    assert status("in_stock") == ["Budget Laptop", "Cheap Phone"]
    assert status("out_of_stock") == ["Flagship Phone", "Mid Phone"]
