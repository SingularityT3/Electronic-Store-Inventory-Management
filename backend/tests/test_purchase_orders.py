"""Purchase order lifecycle API tests for Issue #21."""

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.audit._internal.models import AuditLog
from app.modules.auth._internal.models import User
from app.modules.notifications._internal.models import Notification
from app.modules.product._internal.models import Category, Product, ProductVariant
from app.modules.purchasing import update_purchase_order_receipt_status
from app.modules.purchasing._internal.models import (
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseOrderReceipt,
    Supplier,
    SupplierProduct,
)
from app.modules.stock._internal.models import Location
from tests.helpers import login


def signed_in(client, make_user, role: str, suffix: str = "") -> tuple[str, User]:
    username = f"po_{role}_{suffix or uuid4().hex[:6]}"
    user = make_user(username, role=role, location_id=1 if role in {"staff", "cashier"} else None)
    assert login(client, username).status_code == 200
    return username, user


def create_fixture_data(
    db: Session, suffix: str | None = None
) -> tuple[Supplier, Location, Product]:
    suffix = suffix or uuid4().hex[:8]
    supplier = Supplier(name=f"PO supplier {suffix}")
    location = Location(name=f"PO location {suffix}", type="warehouse", is_active=True)
    category = Category(name=f"PO category {suffix}", parent_id=None)
    db.add_all([supplier, location, category])
    db.flush()
    product = Product(
        sku=f"PO-{suffix}",
        name=f"PO product {suffix}",
        category_id=category.id,
        brand="Test",
        price=Decimal("120.00"),
        is_active=True,
    )
    db.add(product)
    db.flush()
    db.add(
        SupplierProduct(
            supplier_id=supplier.id,
            product_id=product.id,
            variant_id=None,
            supplier_sku=f"SUP-{suffix}",
            supplier_price=Decimal("82.50"),
        )
    )
    db.commit()
    return supplier, location, product


def create_payload(supplier: Supplier, location: Location, product: Product) -> dict:
    return {
        "supplier_id": supplier.id,
        "location_id": location.id,
        "expected_delivery_date": "2026-11-10",
        "notes": "deliver during business hours",
        "lines": [
            {
                "product_id": product.id,
                "quantity_ordered": 3,
                "unit_price": "82.50",
            }
        ],
    }


def test_create_list_view_edit_and_submit_po_calculates_totals_and_audits(client, make_user, db):
    admin = make_user("po_status_admin", role="admin")
    _, user = signed_in(client, make_user, "manager")
    supplier, location, product = create_fixture_data(db)

    created = client.post(
        "/api/purchasing/purchase-orders",
        json=create_payload(supplier, location, product),
    )
    assert created.status_code == 201, created.text
    order = created.json()
    assert order["status"] == "draft"
    assert order["expected_delivery_date"] == "2026-11-10"
    assert order["supplier_name"] == supplier.name
    assert order["total"] == "247.50"
    assert order["lines"][0]["unit_price"] == "82.50"

    catalog_entry = db.scalar(
        select(SupplierProduct).where(
            SupplierProduct.supplier_id == supplier.id,
            SupplierProduct.product_id == product.id,
        )
    )
    assert catalog_entry is not None
    catalog_entry.supplier_price = Decimal("99.00")
    db.commit()
    updated = client.patch(
        f"/api/purchasing/purchase-orders/{order['id']}",
        json={"notes": "updated instructions"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["total"] == "247.50"
    assert updated.json()["lines"][0]["unit_price"] == "82.50"
    updated = client.patch(
        f"/api/purchasing/purchase-orders/{order['id']}",
        json={"lines": [{"product_id": product.id, "quantity_ordered": 4, "unit_price": "80.00"}]},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["total"] == "320.00"
    assert updated.json()["notes"] == "updated instructions"
    assert client.get(f"/api/purchasing/purchase-orders/{order['id']}").json() == updated.json()
    listed = client.get("/api/purchasing/purchase-orders")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == order["id"]

    submitted = client.post(f"/api/purchasing/purchase-orders/{order['id']}/submit")
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "submitted"
    assert submitted.json()["submitted_at"] is not None
    assert (
        client.patch(
            f"/api/purchasing/purchase-orders/{order['id']}", json={"notes": "no longer draft"}
        ).status_code
        == 409
    )

    notifications = db.scalars(
        select(Notification).where(
            Notification.recipient_user_id == user.id,
            Notification.reference_id == order["id"],
        )
    ).all()
    assert len(notifications) == 1
    assert notifications[0].type == "po_status"
    assert f"{order['po_number']}: Submitted" == notifications[0].message
    admin_notification = db.scalar(
        select(Notification).where(
            Notification.recipient_user_id == admin.id,
            Notification.reference_id == order["id"],
        )
    )
    assert admin_notification is not None
    assert admin_notification.message == f"{order['po_number']}: Submitted"
    actions = set(
        db.scalars(
            select(AuditLog.action).where(
                AuditLog.entity_type == "purchase_order",
                AuditLog.entity_id == str(order["id"]),
            )
        )
    )
    assert {
        "purchase_order_created",
        "purchase_order_updated",
        "purchase_order_status_changed",
    } <= actions


@pytest.mark.parametrize("quantity", [0, -1])
def test_purchase_order_rejects_zero_and_negative_quantities(client, make_user, db, quantity):
    signed_in(client, make_user, "manager")
    supplier, location, product = create_fixture_data(db)
    payload = create_payload(supplier, location, product)
    payload["lines"][0]["quantity_ordered"] = quantity

    response = client.post("/api/purchasing/purchase-orders", json=payload)
    assert response.status_code == 422


def test_purchase_order_requires_active_supplier_location_and_catalog_line(client, make_user, db):
    signed_in(client, make_user, "manager")
    supplier, location, product = create_fixture_data(db)
    payload = create_payload(supplier, location, product)

    invalid_supplier = client.post(
        "/api/purchasing/purchase-orders", json={**payload, "supplier_id": supplier.id + 100}
    )
    assert invalid_supplier.status_code == 404
    invalid_location = client.post(
        "/api/purchasing/purchase-orders", json={**payload, "location_id": location.id + 100}
    )
    assert invalid_location.status_code == 404
    not_catalogued = client.post(
        "/api/purchasing/purchase-orders",
        json={
            **payload,
            "lines": [{**payload["lines"][0], "product_id": product.id + 100}],
        },
    )
    assert not_catalogued.status_code == 404

    supplier.is_active = False
    db.commit()
    inactive = client.post("/api/purchasing/purchase-orders", json=payload)
    assert inactive.status_code == 422


def test_purchase_order_accepts_supplier_catalog_variant(client, make_user, db):
    signed_in(client, make_user, "manager")
    supplier, location, product = create_fixture_data(db)
    variant = ProductVariant(
        product_id=product.id,
        sku=f"{product.sku}-BLACK",
        attributes={"color": "black"},
    )
    db.add(variant)
    db.flush()
    db.add(
        SupplierProduct(
            supplier_id=supplier.id,
            product_id=product.id,
            variant_id=variant.id,
            supplier_sku="SUP-BLACK",
            supplier_price=Decimal("90.00"),
        )
    )
    db.commit()
    payload = create_payload(supplier, location, product)
    payload["lines"] = [
        {
            "product_id": product.id,
            "variant_id": variant.id,
            "quantity_ordered": 2,
            "unit_price": "90.00",
        }
    ]
    response = client.post("/api/purchasing/purchase-orders", json=payload)
    assert response.status_code == 201, response.text
    assert response.json()["lines"][0]["sku"] == variant.sku
    assert response.json()["total"] == "180.00"


def test_cancelled_orders_are_excluded_from_pending_orders(client, make_user, db):
    _, creator = signed_in(client, make_user, "manager")
    supplier, location, product = create_fixture_data(db)
    payload = create_payload(supplier, location, product)
    created = client.post("/api/purchasing/purchase-orders", json=payload).json()
    cancelled = client.post(f"/api/purchasing/purchase-orders/{created['id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    pending = client.get("/api/purchasing/purchase-orders/pending")
    assert pending.status_code == 200
    assert all(order["id"] != created["id"] for order in pending.json())
    assert (
        client.get("/api/purchasing/purchase-orders?order_status=cancelled").json()[0]["id"]
        == created["id"]
    )
    notification = db.scalar(
        select(Notification).where(
            Notification.recipient_user_id == creator.id,
            Notification.reference_id == created["id"],
        )
    )
    assert notification is not None
    assert notification.message == f"{created['po_number']}: Cancelled"
    assert client.post(f"/api/purchasing/purchase-orders/{created['id']}/cancel").status_code == 409


def test_receipt_hook_advances_lifecycle_notifies_and_freezes_lines(client, make_user, db):
    username, creator = signed_in(client, make_user, "manager")
    supplier, location, product = create_fixture_data(db)
    created = client.post(
        "/api/purchasing/purchase-orders",
        json=create_payload(supplier, location, product),
    ).json()
    order = db.get(PurchaseOrder, created["id"])
    assert order is not None
    line = db.scalar(
        select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == order.id)
    )
    assert line is not None
    client.post(f"/api/purchasing/purchase-orders/{order.id}/submit")

    receipt = PurchaseOrderReceipt(
        purchase_order_id=order.id,
        received_by=creator.id,
        notes="first delivery",
    )
    db.add(receipt)
    line.quantity_received = 1
    db.commit()
    assert (
        update_purchase_order_receipt_status(
            db,
            purchase_order_id=order.id,
            actor_id=creator.id,
            actor_username=username,
        )
        == "partially_received"
    )
    db.commit()
    partial = client.get(f"/api/purchasing/purchase-orders/{order.id}")
    assert partial.json()["status"] == "partially_received"
    locked = client.patch(
        f"/api/purchasing/purchase-orders/{order.id}",
        json={"lines": [{"product_id": product.id, "quantity_ordered": 4, "unit_price": "82.50"}]},
    )
    assert locked.status_code == 409
    assert locked.json()["detail"] == "Cannot modify PO after receipt has started"
    assert client.post(f"/api/purchasing/purchase-orders/{order.id}/cancel").status_code == 409

    line.quantity_received = line.quantity_ordered
    db.commit()
    assert (
        update_purchase_order_receipt_status(
            db,
            purchase_order_id=order.id,
            actor_id=creator.id,
            actor_username=username,
        )
        == "received"
    )
    db.commit()
    assert client.get(f"/api/purchasing/purchase-orders/{order.id}").json()["status"] == "received"
    events = db.scalars(
        select(Notification.message)
        .where(Notification.reference_id == order.id, Notification.recipient_user_id == creator.id)
        .order_by(Notification.id)
    ).all()
    assert events == [
        f"{order.po_number}: Submitted",
        f"{order.po_number}: Partially Received",
        f"{order.po_number}: Received",
    ]
    assert creator.role == "manager"


def test_admin_can_manage_purchase_orders_staff_and_cashier_are_denied(client, make_user, db):
    supplier, location, product = create_fixture_data(db)
    _username, admin = signed_in(client, make_user, "admin")
    payload = create_payload(supplier, location, product)
    created = client.post("/api/purchasing/purchase-orders", json=payload)
    assert created.status_code == 201, created.text
    assert client.get("/api/purchasing/purchase-orders").status_code == 200
    client.post("/api/auth/logout")

    for role in ("staff", "cashier"):
        signed_in(client, make_user, role)
        assert client.get("/api/purchasing/purchase-orders").status_code == 403
        assert (
            client.get(f"/api/purchasing/purchase-orders/{created.json()['id']}").status_code == 403
        )
        assert client.post("/api/purchasing/purchase-orders", json=payload).status_code == 403
        assert (
            client.patch(
                f"/api/purchasing/purchase-orders/{created.json()['id']}", json={"notes": "blocked"}
            ).status_code
            == 403
        )
        assert (
            client.post(
                f"/api/purchasing/purchase-orders/{created.json()['id']}/submit"
            ).status_code
            == 403
        )
        assert (
            client.post(
                f"/api/purchasing/purchase-orders/{created.json()['id']}/cancel"
            ).status_code
            == 403
        )
        client.post("/api/auth/logout")

    assert admin.role == "admin"


def test_admin_creator_is_notified_of_po_status_changes(client, make_user, db):
    _username, admin = signed_in(client, make_user, "admin")
    supplier, location, product = create_fixture_data(db)
    created = client.post(
        "/api/purchasing/purchase-orders", json=create_payload(supplier, location, product)
    ).json()
    assert client.post(f"/api/purchasing/purchase-orders/{created['id']}/submit").status_code == 200
    recipients = db.scalars(
        select(Notification.recipient_user_id).where(Notification.reference_id == created["id"])
    ).all()
    assert admin.id in recipients


def test_purchase_order_rejects_deleted_products(client, make_user, db):
    signed_in(client, make_user, "manager")
    supplier, location, product = create_fixture_data(db)
    product.is_active = False
    db.commit()
    response = client.post(
        "/api/purchasing/purchase-orders", json=create_payload(supplier, location, product)
    )
    assert response.status_code == 404
