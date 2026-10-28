"""Stock alert API and threshold reevaluation."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select

from app.modules.audit._internal.models import AuditLog
from app.modules.notifications._internal.models import Notification, StockAlert
from app.modules.product._internal.models import Category, Product
from app.modules.reporting.service import reorder_rows
from app.modules.stock import reevaluate_stock_alert, update_stock
from app.modules.stock._internal.models import Location, StockLevel
from tests.helpers import login


def create_alert_item(db, *, quantity: int, threshold: int):
    suffix = uuid4().hex[:10]
    location = Location(name=f"Alert Store {suffix}", type="store")
    other = Location(name=f"Alert Warehouse {suffix}", type="warehouse")
    category = Category(name=f"Alert Category {suffix}")
    db.add_all([location, other, category])
    db.flush()
    product = Product(
        sku=f"ALERT-{suffix}",
        name=f"Alert Product {suffix}",
        category_id=category.id,
        brand="Test",
        price=Decimal("10"),
    )
    db.add(product)
    db.flush()
    levels = [
        StockLevel(
            product_id=product.id,
            location_id=target.id,
            quantity=quantity if target == location else 50,
            reorder_threshold=threshold,
        )
        for target in (location, other)
    ]
    db.add_all(levels)
    db.commit()
    return product, location, other, levels[0]


def test_shared_stock_updates_create_distinct_alerts_and_clear_on_recovery(client, make_user, db):
    product, location, _, level = create_alert_item(db, quantity=6, threshold=5)
    make_user("alert_lifecycle_manager", role="manager")
    assert login(client, "alert_lifecycle_manager").status_code == 200

    update_stock(
        db,
        product_id=product.id,
        variant_id=None,
        location_id=location.id,
        quantity_delta=-1,
        movement_type="sale",
    )
    low = client.get("/api/notifications/alerts").json()
    assert len(low) == 1
    assert (low[0]["alert_type"], low[0]["quantity"], low[0]["threshold"]) == (
        "low_stock",
        5,
        5,
    )

    update_stock(
        db,
        product_id=product.id,
        variant_id=None,
        location_id=location.id,
        quantity_delta=-5,
        movement_type="sale",
    )
    out_of_stock = client.get("/api/notifications/alerts").json()
    assert len(out_of_stock) == 1
    assert out_of_stock[0]["alert_type"] == "out_of_stock"
    assert out_of_stock[0]["id"] == low[0]["id"]

    update_stock(
        db,
        product_id=product.id,
        variant_id=None,
        location_id=location.id,
        quantity_delta=6,
        movement_type="receipt",
    )
    assert client.get("/api/notifications/alerts").json() == []
    db.refresh(level)
    assert level.quantity == 6
    alert = db.scalar(select(StockAlert).where(StockAlert.id == low[0]["id"]))
    assert alert.alert_type is None
    assert alert.resolved_at is not None


def test_alerts_are_location_scoped_and_align_with_reorder_report(client, make_user, db):
    product, location, other, _ = create_alert_item(db, quantity=2, threshold=3)
    reevaluate_stock_alert(db, product_id=product.id, variant_id=None, location_id=location.id)
    make_user("alert_scope_manager", role="manager")
    assert login(client, "alert_scope_manager").status_code == 200

    alerts = client.get("/api/notifications/alerts").json()
    assert {alert["location_id"] for alert in alerts} == {location.id}
    reorder_positions = {
        (position.product_id, position.location_id)
        for position, _ in reorder_rows(db)
        if position.product_id == product.id
    }
    assert {(alert["product_id"], alert["location_id"]) for alert in alerts} == reorder_positions

    make_user("alert_scope_staff", role="staff", location_id=location.id)
    assert login(client, "alert_scope_staff").status_code == 200
    assert {alert["location_id"] for alert in client.get("/api/notifications/alerts").json()} == {
        location.id
    }
    assert client.get(f"/api/notifications/alerts?location_id={other.id}").status_code == 403


def test_threshold_changes_reevaluate_immediately_and_cashier_is_denied(client, make_user, db):
    product, location, _, _ = create_alert_item(db, quantity=12, threshold=5)
    make_user("alert_threshold_manager", role="manager")
    assert login(client, "alert_threshold_manager").status_code == 200
    payload = {
        "product_id": product.id,
        "location_id": location.id,
        "reorder_threshold": 15,
    }
    response = client.patch("/api/stock/levels/reorder-settings", json=payload)
    assert response.status_code == 200, response.text
    alerts = client.get("/api/notifications/alerts").json()
    assert len(alerts) == 1
    assert (alerts[0]["quantity"], alerts[0]["threshold"]) == (12, 15)

    payload["reorder_threshold"] = 10
    assert client.patch("/api/stock/levels/reorder-settings", json=payload).status_code == 200
    assert client.get("/api/notifications/alerts").json() == []

    make_user("alert_threshold_cashier", role="cashier", location_id=location.id)
    assert login(client, "alert_threshold_cashier").status_code == 200
    assert client.get("/api/notifications/alerts").status_code == 403


def test_threshold_above_saved_reorder_to_level_is_a_validation_error(client, make_user, db):
    product, location, _, level = create_alert_item(db, quantity=12, threshold=5)
    level.reorder_to_level = 10
    db.commit()
    make_user("alert_reorder_to_manager", role="manager")
    assert login(client, "alert_reorder_to_manager").status_code == 200
    payload = {"product_id": product.id, "location_id": location.id, "reorder_threshold": 20}
    response = client.patch("/api/stock/levels/reorder-settings", json=payload)
    assert response.status_code == 422, response.text
    payload["reorder_to_level"] = 40
    response = client.patch("/api/stock/levels/reorder-settings", json=payload)
    assert response.status_code == 200, response.text
    actions = db.scalars(select(AuditLog.action)).all()
    assert "reorder_settings_updated" in actions


def test_notification_feed_is_recipient_scoped_and_chronological(client, make_user, db):
    manager = make_user("notification_feed_manager", role="manager")
    other_manager = make_user("notification_feed_other", role="manager")
    now = datetime.now(UTC)
    db.add_all(
        [
            Notification(
                recipient_user_id=manager.id,
                type="po_status",
                title="Purchase order status changed",
                message="PO-3010: Received",
                location_id=None,
                reference_type="purchase_order",
                reference_id=3010,
                created_at=now,
            ),
            Notification(
                recipient_user_id=manager.id,
                type="po_status",
                title="Purchase order status changed",
                message="PO-3010: Submitted",
                location_id=None,
                reference_type="purchase_order",
                reference_id=3010,
                created_at=now - timedelta(minutes=5),
            ),
            Notification(
                recipient_user_id=other_manager.id,
                type="po_status",
                title="Purchase order status changed",
                message="PO-9999: Received",
                location_id=None,
                reference_type="purchase_order",
                reference_id=9999,
                created_at=now - timedelta(minutes=10),
            ),
        ]
    )
    db.commit()
    assert login(client, manager.username).status_code == 200

    response = client.get("/api/notifications")

    assert response.status_code == 200
    assert [row["message"] for row in response.json()] == [
        "PO-3010: Submitted",
        "PO-3010: Received",
    ]
    timestamps = [
        datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")) for row in response.json()
    ]
    assert timestamps == sorted(timestamps)
    assert all(row["created_at"] for row in response.json())


def test_notification_feed_respects_role_permissions(client, make_user, db):
    staff = make_user("notification_feed_staff", role="staff", location_id=1)
    db.add(
        Notification(
            recipient_user_id=staff.id,
            type="po_status",
            title="Purchase order status changed",
            message="PO-3010: Submitted",
            location_id=None,
            reference_type="purchase_order",
            reference_id=3010,
        )
    )
    db.commit()
    assert login(client, staff.username).status_code == 200
    staff_response = client.get("/api/notifications")
    assert staff_response.status_code == 200
    assert staff_response.json()[0]["message"] == "PO-3010: Submitted"

    client.post("/api/auth/logout")
    cashier = make_user("notification_feed_cashier", role="cashier", location_id=1)
    assert login(client, cashier.username).status_code == 200
    assert client.get("/api/notifications").status_code == 403
