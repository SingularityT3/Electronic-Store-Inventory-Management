"""Manual stock adjustments (FR-2.4, UC-08)."""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.modules.audit._internal.models import AuditLog
from app.modules.stock._internal.models import ItemCost, StockLevel, StockMovement
from tests.helpers import login
from tests.test_stock_transfers import create_transfer_data


def adjust(client, product, location, change, reason="Damaged", **extra):
    return client.post(
        "/api/stock/adjustments",
        json={
            "product_id": product.id,
            "location_id": location.id,
            "quantity_change": change,
            "reason": reason,
            **extra,
        },
    )


def quantity(db, product, location) -> int:
    db.expire_all()
    return db.scalar(
        select(StockLevel.quantity).where(
            StockLevel.product_id == product.id, StockLevel.location_id == location.id
        )
    )


def test_negative_adjustment_reduces_stock_and_logs_reason(client, make_user, db):
    source, _, product = create_transfer_data(db, source_quantity=10)
    db.add(ItemCost(product_id=product.id, average_cost=Decimal("10.00")))
    db.commit()
    make_user("adjust_manager", role="manager")
    assert login(client, "adjust_manager").status_code == 200

    response = adjust(client, product, source, -5, "Damaged", reason_code="damage")
    assert response.status_code == 201, response.text
    assert response.json()["quantity"] == 5
    assert quantity(db, product, source) == 5

    movement = db.scalar(select(StockMovement).where(StockMovement.movement_type == "adjustment"))
    assert (movement.quantity_change, movement.reason, movement.reason_code) == (
        -5,
        "Damaged",
        "damage",
    )
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "stock_updated"))
    assert audit.username == "adjust_manager"
    assert audit.occurred_at is not None
    assert audit.before == {"quantity": 10}
    assert audit.after["quantity_delta"] == -5
    assert audit.after["reason"] == "Damaged"
    assert "Damaged" in audit.details

    valuation = client.get("/api/reporting/valuation").json()["items"]
    rows = [r for r in valuation if r["product_id"] == product.id]
    assert [(r["quantity"], Decimal(r["value"])) for r in rows] == [(5, Decimal("50.00"))]


def test_positive_adjustment_increases_stock(client, make_user, db):
    source, _, product = create_transfer_data(db, source_quantity=10)
    make_user("adjust_staff_mgr", role="manager")
    login(client, "adjust_staff_mgr")
    response = adjust(client, product, source, 5, "Found during count")
    assert response.status_code == 201, response.text
    assert quantity(db, product, source) == 15


@pytest.mark.parametrize("reason", ["", "   "])
def test_blank_reason_is_rejected_and_stock_unchanged(client, make_user, db, reason):
    source, _, product = create_transfer_data(db, source_quantity=10)
    make_user("adjust_blank", role="manager")
    login(client, "adjust_blank")
    response = adjust(client, product, source, -1, reason)
    assert response.status_code == 422
    assert response.json()["detail"] == "Reason is required for stock adjustment"
    assert quantity(db, product, source) == 10


def test_adjustment_below_zero_is_blocked(client, make_user, db):
    source, _, product = create_transfer_data(db, source_quantity=3)
    make_user("adjust_neg", role="manager")
    login(client, "adjust_neg")
    response = adjust(client, product, source, -4)
    assert response.status_code == 409
    assert response.json()["detail"] == "Adjustment would result in negative stock"
    assert quantity(db, product, source) == 3
    adjustments = select(StockMovement).where(StockMovement.movement_type == "adjustment")
    assert db.scalar(adjustments) is None


def test_cashier_is_denied(client, make_user, db):
    source, _, product = create_transfer_data(db, source_quantity=10)
    make_user("adjust_cashier", role="cashier", location_id=source.id)
    login(client, "adjust_cashier")
    assert adjust(client, product, source, -1).status_code == 403
    assert quantity(db, product, source) == 10
