"""Per-location low/out-of-stock alert state (#19)."""

from decimal import Decimal
from uuid import uuid4

import pytest

from app.modules.notifications import active_stock_alerts
from app.modules.notifications import reevaluate_stock_alert as persist_alert
from app.modules.product._internal.models import Category, Product
from app.modules.reporting.service import reorder_rows
from app.modules.stock import reevaluate_stock_alert
from app.modules.stock._internal.models import Location, StockLevel
from tests.helpers import login


def make_item(db, *, quantity: int, threshold: int, locations: tuple[str, ...] = ("Alert Store",)):
    token = uuid4().hex[:10]
    category = Category(name=f"Alert Category {token}")
    db.add(category)
    db.flush()
    product = Product(
        sku=f"ALERT-{token}",
        name=f"Alert Product {token}",
        category_id=category.id,
        brand="Test",
        price=Decimal("10.00"),
    )
    location_rows = [Location(name=f"{name} {token}", type="store") for name in locations]
    db.add_all([product, *location_rows])
    db.flush()
    levels = [
        StockLevel(
            product_id=product.id,
            location_id=location.id,
            quantity=quantity,
            reorder_threshold=threshold,
        )
        for location in location_rows
    ]
    db.add_all(levels)
    db.commit()
    return product, location_rows, levels


def reevaluate(db, product: Product, location: Location) -> None:
    reevaluate_stock_alert(
        db,
        product_id=product.id,
        variant_id=None,
        location_id=location.id,
    )


def sign_in(client, make_user, username: str, role: str, location_id: int | None = None):
    make_user(username, role=role, location_id=location_id)
    assert login(client, username).status_code == 200


def test_alert_threshold_zero_recovery_and_repeated_crossings(client, make_user, db):
    product, locations, levels = make_item(db, quantity=6, threshold=5)
    location = locations[0]
    level = levels[0]
    sign_in(client, make_user, "alert_manager", "manager")

    reevaluate(db, product, location)
    assert client.get("/api/notifications/alerts").json() == []

    level.quantity = 5
    db.flush()
    reevaluate(db, product, location)
    first = client.get("/api/notifications/alerts").json()
    assert len(first) == 1
    assert first[0]["alert_type"] == "low_stock"
    assert first[0]["quantity"] == 5
    assert first[0]["threshold"] == 5

    level.quantity = 0
    db.flush()
    reevaluate(db, product, location)
    out_of_stock = client.get("/api/notifications/alerts").json()
    assert len(out_of_stock) == 1
    assert out_of_stock[0]["id"] == first[0]["id"]
    assert out_of_stock[0]["alert_type"] == "out_of_stock"

    level.quantity = 6
    db.flush()
    reevaluate(db, product, location)
    assert client.get("/api/notifications/alerts").json() == []

    level.quantity = 2
    db.flush()
    reevaluate(db, product, location)
    recovered = client.get("/api/notifications/alerts").json()
    assert len(recovered) == 1
    assert recovered[0]["id"] == first[0]["id"]
    assert recovered[0]["alert_type"] == "low_stock"
    assert recovered[0]["product_id"] == product.id
    assert recovered[0]["location_id"] == location.id


def test_alerts_are_location_specific_and_staff_scoped(client, make_user, db):
    product, locations, levels = make_item(
        db,
        quantity=1,
        threshold=2,
        locations=("Staff Alert", "Other Alert"),
    )
    levels[1].quantity = 3
    db.flush()
    for location in locations:
        reevaluate(db, product, location)

    sign_in(client, make_user, "alert_manager_scope", "manager")
    all_alerts = client.get("/api/notifications/alerts")
    assert {alert["location_id"] for alert in all_alerts.json()} == {locations[0].id}

    sign_in(client, make_user, "alert_staff", "staff", locations[0].id)

    response = client.get("/api/notifications/alerts")
    assert response.status_code == 200
    assert {alert["location_id"] for alert in response.json()} == {locations[0].id}
    assert client.get(f"/api/notifications/alerts?location_id={locations[1].id}").status_code == 403


def test_cashier_cannot_view_stock_alerts(client, make_user, db):
    location = Location(name=f"Cashier Alert {uuid4().hex[:10]}", type="store")
    db.add(location)
    db.commit()
    sign_in(client, make_user, "alert_cashier", "cashier", location.id)
    assert client.get("/api/notifications/alerts").status_code == 403


def test_threshold_update_reevaluates_immediately_and_validates_values(client, make_user, db):
    product, locations, levels = make_item(db, quantity=4, threshold=1)
    location = locations[0]
    sign_in(client, make_user, "threshold_manager", "manager")
    payload = {
        "product_id": product.id,
        "location_id": location.id,
        "reorder_threshold": 4,
    }

    updated = client.patch("/api/stock/levels/reorder-settings", json=payload)
    assert updated.status_code == 200, updated.text
    assert updated.json()["reorder_threshold"] == 4
    alerts = client.get("/api/notifications/alerts").json()
    assert len(alerts) == 1
    assert alerts[0]["quantity"] == 4
    assert alerts[0]["threshold"] == 4

    payload["reorder_threshold"] = 3
    updated = client.patch("/api/stock/levels/reorder-settings", json=payload)
    assert updated.status_code == 200
    assert client.get("/api/notifications/alerts").json() == []

    payload["reorder_threshold"] = 4
    payload["reorder_to_level"] = 3
    assert client.patch("/api/stock/levels/reorder-settings", json=payload).status_code == 422

    payload["reorder_to_level"] = 5
    payload["product_id"] = 999999
    assert client.patch("/api/stock/levels/reorder-settings", json=payload).status_code == 404


def test_staff_can_only_update_threshold_for_assigned_location(client, make_user, db):
    product, locations, _ = make_item(
        db,
        quantity=4,
        threshold=1,
        locations=("Assigned Threshold", "Other Threshold"),
    )
    sign_in(client, make_user, "threshold_staff", "staff", locations[0].id)
    response = client.patch(
        "/api/stock/levels/reorder-settings",
        json={
            "product_id": product.id,
            "location_id": locations[1].id,
            "reorder_threshold": 5,
        },
    )
    assert response.status_code == 403


def test_alerts_match_reorder_report_rows(client, make_user, db):
    product, locations, _ = make_item(db, quantity=2, threshold=3)
    reevaluate(db, product, locations[0])
    sign_in(client, make_user, "report_alert_manager", "manager")

    alerts = client.get("/api/notifications/alerts").json()
    reorder_keys = {
        (position.product_id, position.variant_id, position.location_id)
        for position, _ in reorder_rows(db)
        if position.product_id == product.id
    }
    alert_keys = {
        (alert["product_id"], alert["variant_id"], alert["location_id"]) for alert in alerts
    }
    assert alert_keys == reorder_keys


def test_negative_alert_facts_fail_without_creating_alert(db):
    with pytest.raises(ValueError, match="must be nonnegative"):
        persist_alert(
            db,
            product_id=1,
            variant_id=None,
            product_name="Invalid quantity",
            sku="INVALID",
            variant_sku=None,
            location_id=1,
            location_name="Nowhere",
            quantity=-1,
            threshold=2,
        )
    assert active_stock_alerts(db) == []
