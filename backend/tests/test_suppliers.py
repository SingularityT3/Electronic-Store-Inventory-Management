"""Supplier and supplier catalog API tests for Issue #20."""

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.audit._internal.models import AuditLog
from app.modules.auth._internal.models import User
from app.modules.product._internal.models import Category, Product
from app.modules.purchasing._internal.models import (
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
    SupplierPriceHistory,
)
from app.modules.stock._internal.models import Location
from tests.helpers import login


def manager(client, make_user, role: str = "manager"):
    username = f"supplier_{role}"
    make_user(username, role=role)
    assert login(client, username).status_code == 200
    return client


def create_supplier(client, name: str = "Acme Supply"):
    response = client.post(
        "/api/purchasing/suppliers",
        json={"name": name, "contact_name": "Morgan Lee", "email": "morgan@example.com"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_product(db: Session) -> Product:
    suffix = uuid4().hex[:8]
    category = Category(name=f"Supplier test category {suffix}", parent_id=None)
    db.add(category)
    db.flush()
    product = Product(
        sku=f"SUP-{suffix}",
        name="Supplier test product",
        category_id=category.id,
        brand="Test",
        price=Decimal("100.00"),
        is_active=True,
    )
    db.add(product)
    db.commit()
    return product


def test_supplier_crud_validates_email_and_records_audit(client, make_user, db):
    client = manager(client, make_user, "manager")
    invalid = client.post(
        "/api/purchasing/suppliers", json={"name": "Invalid Email", "email": "not-an-email"}
    )
    assert invalid.status_code == 422
    assert invalid.json()["detail"] == "Invalid email format"

    supplier = create_supplier(client)
    updated = client.patch(
        f"/api/purchasing/suppliers/{supplier['id']}",
        json={"name": "Acme Electronics", "email": "sales@acme.example"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Acme Electronics"
    assert updated.json()["email"] == "sales@acme.example"
    invalid_update = client.patch(
        f"/api/purchasing/suppliers/{supplier['id']}", json={"email": "bad@domain"}
    )
    assert invalid_update.status_code == 422
    assert invalid_update.json()["detail"] == "Invalid email format"

    audit_actions = set(
        db.scalars(
            select(AuditLog.action).where(
                AuditLog.module == "purchasing",
                AuditLog.entity_type == "supplier",
                AuditLog.entity_id == str(supplier["id"]),
            )
        )
    )
    assert audit_actions == {"supplier_created", "supplier_updated"}

    client.post("/api/auth/logout")
    admin = manager(client, make_user, "admin")
    assert admin.get("/api/purchasing/suppliers").status_code == 200
    assert any(row["id"] == supplier["id"] for row in admin.get("/api/purchasing/suppliers").json())


def test_supplier_duplicate_name_and_nonexistent_id(client, make_user):
    client = manager(client, make_user)
    create_supplier(client)
    duplicate = client.post("/api/purchasing/suppliers", json={"name": "Acme Supply"})
    assert duplicate.status_code == 409
    missing = client.patch("/api/purchasing/suppliers/999999", json={"name": "Missing"})
    assert missing.status_code == 404
    assert client.delete("/api/purchasing/suppliers/999999").status_code == 404


def test_catalog_crud_validates_prices_references_and_duplicate_associations(client, make_user, db):
    client = manager(client, make_user)
    supplier = create_supplier(client)
    product = create_product(db)
    path = f"/api/purchasing/suppliers/{supplier['id']}/products"
    payload = {
        "product_id": product.id,
        "supplier_sku": "ACME-PHONE",
        "supplier_price": "87.50",
    }
    added = client.post(path, json=payload)
    assert added.status_code == 201, added.text
    assert added.json()["product_id"] == product.id
    assert added.json()["supplier_price"] == "87.50"

    duplicate = client.post(path, json=payload)
    assert duplicate.status_code == 409
    negative_price = client.post(
        path, json={**payload, "product_id": product.id + 100, "supplier_price": "-1"}
    )
    assert negative_price.status_code == 422
    missing_product = client.post(path, json={**payload, "product_id": product.id + 100})
    assert missing_product.status_code == 404
    wrong_variant = client.post(path, json={**payload, "variant_id": 999999})
    assert wrong_variant.status_code == 422

    entry_id = added.json()["id"]
    changed = client.patch(
        f"{path}/{entry_id}", json={"supplier_sku": "ACME-NEW", "supplier_price": "91.25"}
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["supplier_sku"] == "ACME-NEW"
    assert changed.json()["supplier_price"] == "91.25"
    assert client.patch(f"{path}/{entry_id}", json={"supplier_price": "-1"}).status_code == 422
    assert client.get(path).json()[0]["supplier_price"] == "91.25"
    assert client.delete(f"{path}/{entry_id}").status_code == 204
    assert client.get(path).json() == []

    actions = set(
        db.scalars(
            select(AuditLog.action).where(
                AuditLog.module == "purchasing",
                AuditLog.entity_type == "supplier_product",
            )
        )
    )
    assert actions == {
        "supplier_product_added",
        "supplier_product_updated",
        "supplier_product_removed",
    }


@pytest.mark.parametrize("status", ["draft", "submitted", "partially_received"])
def test_supplier_deactivation_is_blocked_by_open_purchase_orders(client, make_user, db, status):
    user = make_user(f"supplier_open_po_{status}", role="manager")
    location = Location(name=f"PO location {status}", type="warehouse")
    supplier = Supplier(name=f"Open PO supplier {status}")
    db.add_all([location, supplier])
    db.flush()
    order = PurchaseOrder(
        po_number=f"PO-{uuid4().hex[:10]}",
        supplier_id=supplier.id,
        location_id=location.id,
        status=status,
        created_by=user.id,
    )
    db.add(order)
    db.commit()
    assert login(client, user.username).status_code == 200

    response = client.delete(f"/api/purchasing/suppliers/{supplier.id}")
    assert response.status_code == 409
    assert response.json()["detail"] == "Cannot delete supplier with open purchase orders"
    assert db.get(Supplier, supplier.id).is_active is True


def test_supplier_deactivation_preserves_purchase_order_prices_and_history(client, make_user, db):
    client = manager(client, make_user)
    supplier = create_supplier(client)
    product = create_product(db)
    user = db.scalar(select(User))
    assert user is not None
    location = Location(name=f"History location {uuid4().hex[:8]}", type="store")
    db.add(location)
    db.flush()
    order = PurchaseOrder(
        po_number=f"PO-{uuid4().hex[:10]}",
        supplier_id=supplier["id"],
        location_id=location.id,
        status="received",
        created_by=user.id,
    )
    db.add(order)
    db.flush()
    line = PurchaseOrderLine(
        purchase_order_id=order.id,
        product_id=product.id,
        variant_id=None,
        quantity_ordered=2,
        quantity_received=2,
        unit_price=Decimal("72.25"),
    )
    db.add(line)
    history = SupplierPriceHistory(
        supplier_id=supplier["id"],
        product_id=product.id,
        variant_id=None,
        unit_price=Decimal("72.25"),
        receipt_line_id=None,
    )
    db.add(history)
    db.commit()

    response = client.patch(
        f"/api/purchasing/suppliers/{supplier['id']}", json={"name": "Acme Renamed"}
    )
    assert response.status_code == 200
    assert client.delete(f"/api/purchasing/suppliers/{supplier['id']}").status_code == 204
    db.expire_all()
    assert db.get(Supplier, supplier["id"]).is_active is False
    assert db.get(PurchaseOrder, order.id).supplier_id == supplier["id"]
    assert db.get(PurchaseOrderLine, line.id).unit_price == Decimal("72.25")
    assert (
        db.scalar(
            select(func.count())
            .select_from(SupplierPriceHistory)
            .where(SupplierPriceHistory.id == history.id)
        )
        == 1
    )
    active_supplier_ids = {
        row["id"] for row in client.get("/api/purchasing/suppliers?active_only=true").json()
    }
    assert supplier["id"] not in active_supplier_ids


@pytest.mark.parametrize("role", ["staff", "cashier"])
def test_staff_and_cashier_are_denied_supplier_management(client, make_user, role):
    client = manager(client, make_user, "manager")
    supplier = create_supplier(client)
    client.post("/api/auth/logout")
    username = f"supplier_denied_{role}"
    make_user(username, role=role, location_id=1)
    assert login(client, username).status_code == 200
    assert client.get("/api/purchasing/suppliers").status_code == 403
    assert client.post("/api/purchasing/suppliers", json={"name": role}).status_code == 403
    catalog_path = f"/api/purchasing/suppliers/{supplier['id']}/products"
    assert client.get(catalog_path).status_code == 403
    assert (
        client.post(
            catalog_path,
            json={"product_id": 1, "supplier_price": "1.00"},
        ).status_code
        == 403
    )
    assert (
        client.patch(f"{catalog_path}/999999", json={"supplier_price": "1.00"}).status_code == 403
    )
    assert client.delete(f"{catalog_path}/999999").status_code == 403
    assert (
        client.patch(
            f"/api/purchasing/suppliers/{supplier['id']}", json={"name": "Denied"}
        ).status_code
        == 403
    )
    assert client.delete(f"/api/purchasing/suppliers/{supplier['id']}").status_code == 403


def test_blank_supplier_name_is_a_validation_error_and_blank_fields_are_cleared(client, make_user):
    client = manager(client, make_user, "manager")
    assert client.post("/api/purchasing/suppliers", json={"name": "   "}).status_code == 422
    supplier = client.post(
        "/api/purchasing/suppliers", json={"name": " Blank Fields ", "email": " ", "phone": ""}
    )
    assert supplier.status_code == 201, supplier.text
    assert (supplier.json()["name"], supplier.json()["email"], supplier.json()["phone"]) == (
        "Blank Fields",
        None,
        None,
    )
    supplier_id = supplier.json()["id"]
    rename = client.patch(f"/api/purchasing/suppliers/{supplier_id}", json={"name": " "})
    assert rename.status_code == 422
