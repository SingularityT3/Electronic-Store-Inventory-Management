"""Tests for returns and restocking (FR-4.2, UC-14, Issue #25)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.audit._internal.models import AuditLog
from app.modules.auth._internal.models import User
from app.modules.auth._internal.passwords import hash_password
from app.modules.product._internal.models import Category, Product
from app.modules.sales._internal.models import (
    Invoice,
    Return,
    ReturnLine,
    Sale,
    SaleLine,
)
from app.modules.stock import (
    receive_batch_stock,
    receive_serial_stock,
    update_stock,
)
from app.modules.stock._internal.models import (
    Location,
    SerialNumber,
    StockLevel,
    StockMovement,
)
from tests.helpers import PASSWORD, SETTINGS, login


def setup_sale_fixture(
    db: Session,
    client: TestClient,
    *,
    tracking_mode: str = "untracked",
    initial_stock: int = 15,
    sold_quantity: int = 3,
    unit_price: Decimal = Decimal("100.00"),
    discount: Decimal = Decimal("0"),
    backdate_days: int = 0,
    location: Location | None = None,
    cashier: User | None = None,
) -> tuple[Location, Product, Sale, Invoice, SaleLine, list[str]]:
    suffix = uuid4().hex[:8]
    if location is None:
        location = Location(name=f"Store {suffix}", type="store")
        db.add(location)
        db.flush()

    category = Category(name=f"Cat {suffix}")
    db.add(category)
    db.flush()

    product = Product(
        sku=f"SKU-{suffix}",
        name=f"Product {suffix}",
        category_id=category.id,
        brand="Brand",
        price=unit_price,
        tracking_mode=tracking_mode,
        is_active=True,
    )
    db.add(product)
    db.flush()

    if cashier is None:
        cashier = User(
            username=f"cashier_{suffix}",
            full_name=f"Cashier {suffix}",
            password_hash=hash_password(PASSWORD),
            role="cashier",
            location_id=location.id,
        )
        db.add(cashier)
        db.flush()

    if tracking_mode == "untracked":
        update_stock(
            db,
            product_id=product.id,
            variant_id=None,
            location_id=location.id,
            quantity_delta=initial_stock,
            movement_type="receipt",
            user_id=cashier.id,
            username=cashier.username,
            record_audit=False,
        )

    serials_sold: list[str] = []
    if tracking_mode == "serial":
        all_serials = [f"SN-{suffix}-{i}" for i in range(initial_stock)]
        receive_serial_stock(
            db,
            product_id=product.id,
            variant_id=None,
            location_id=location.id,
            serial_numbers=all_serials,
            user_id=cashier.id,
            username=cashier.username,
            reference_type="po_receipt_line",
            reference_id=1,
        )
        serials_sold = all_serials[:sold_quantity]
    elif tracking_mode == "batch":
        receive_batch_stock(
            db,
            product_id=product.id,
            variant_id=None,
            location_id=location.id,
            batch_number=f"BATCH-{suffix}",
            quantity=initial_stock,
            user_id=cashier.id,
            username=cashier.username,
            reference_type="po_receipt_line",
            reference_id=1,
        )

    db.commit()

    login(client, cashier.username)
    subtotal = unit_price * sold_quantity - discount
    total = (subtotal * Decimal("1.18")).quantize(Decimal("0.01"))

    line_payload: dict[str, object] = {
        "product_id": product.id,
        "quantity": sold_quantity,
        "discount": str(discount),
        "discount_type": "amount",
    }
    if serials_sold:
        line_payload["serial_numbers"] = serials_sold

    resp = client.post(
        "/api/sales",
        json={
            "location_id": location.id,
            "lines": [line_payload],
            "payments": [{"method": "cash", "amount": str(total)}],
        },
    )
    assert resp.status_code == 201, resp.text
    sale_data = resp.json()
    sale_id = sale_data["id"]

    sale = db.get(Sale, sale_id)
    assert sale is not None
    invoice = db.scalar(select(Invoice).where(Invoice.sale_id == sale_id))
    assert invoice is not None
    sale_line = db.scalar(select(SaleLine).where(SaleLine.sale_id == sale_id))
    assert sale_line is not None

    if backdate_days > 0:
        backdated = datetime.now(UTC) - timedelta(days=backdate_days)
        sale.sold_at = backdated
        db.commit()

    return location, product, sale, invoice, sale_line, serials_sold


def test_fr4_2_ut_1_valid_return_generates_credit_note(client, db, make_user):
    location, product, sale, invoice, sale_line, _ = setup_sale_fixture(
        db, client, backdate_days=5, sold_quantity=2
    )

    resp = client.post(
        "/api/sales/returns",
        json={
            "invoice_number": str(invoice.invoice_number),
            "lines": [
                {
                    "sale_line_id": sale_line.id,
                    "quantity": 1,
                    "condition": "resaleable",
                }
            ],
            "reason": "Changed mind",
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()

    assert data["credit_note_number"].startswith("CN-")
    assert data["invoice_number"] == invoice.invoice_number
    assert data["sale_id"] == sale.id
    assert Decimal(data["refund_total"]) > Decimal("0")
    assert len(data["lines"]) == 1
    assert data["lines"][0]["restocked"] is True
    assert data["lines"][0]["condition"] == "resaleable"

    ret_id = data["return_id"]
    ret_row = db.get(Return, ret_id)
    assert ret_row is not None
    assert ret_row.sale_id == sale.id
    ret_lines = db.scalars(select(ReturnLine).where(ReturnLine.return_id == ret_id)).all()
    assert len(ret_lines) == 1
    assert ret_lines[0].refund_amount == Decimal(data["lines"][0]["refund_amount"])


def test_fr4_2_ut_2_resaleable_unit_restocks_inventory(client, db, make_user):
    # Initial stock 15, sold 3 -> stock is 12
    location, product, sale, invoice, sale_line, _ = setup_sale_fixture(
        db, client, initial_stock=15, sold_quantity=3
    )
    stock_before = db.scalar(
        select(StockLevel.quantity).where(
            StockLevel.product_id == product.id, StockLevel.location_id == location.id
        )
    )
    assert stock_before == 12

    resp = client.post(
        "/api/sales/returns",
        json={
            "invoice_number": invoice.invoice_number,
            "lines": [
                {
                    "sale_line_id": sale_line.id,
                    "quantity": 1,
                    "condition": "resaleable",
                }
            ],
            "reason": "Customer returned unopened item",
        },
    )
    assert resp.status_code == 201, resp.text
    ret_data = resp.json()

    stock_after = db.scalar(
        select(StockLevel.quantity).where(
            StockLevel.product_id == product.id, StockLevel.location_id == location.id
        )
    )
    assert stock_after == 13

    movement = db.scalar(
        select(StockMovement).where(
            StockMovement.reference_type == "return",
            StockMovement.reference_id == ret_data["return_id"],
        )
    )
    assert movement is not None
    assert movement.movement_type == "return"
    assert movement.quantity_change == 1
    assert movement.location_id == location.id


def test_fr4_2_ut_3_invoice_lookup_valid_and_invalid(client, db, make_user):
    location, product, sale, invoice, sale_line, _ = setup_sale_fixture(db, client)

    for invalid in ["99999", "INV-99999", "abc", "INV-GARBAGE", ""]:
        resp = client.get(f"/api/sales/by-invoice/{invalid}")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Invoice not found"

    assert db.scalar(select(func.count(Return.id))) == 0

    resp_bare = client.get(f"/api/sales/by-invoice/{invoice.invoice_number}")
    assert resp_bare.status_code == 200
    assert resp_bare.json()["invoice"]["invoice_number"] == invoice.invoice_number

    resp_prefixed = client.get(f"/api/sales/by-invoice/INV-{invoice.invoice_number:06d}")
    assert resp_prefixed.status_code == 200
    assert resp_prefixed.json()["id"] == sale.id

    resp_lower = client.get(f"/api/sales/by-invoice/inv-{invoice.invoice_number}")
    assert resp_lower.status_code == 200
    assert resp_lower.json()["id"] == sale.id


def test_fr4_2_it_1_damaged_line_not_restocked_and_mixed_return(client, db, make_user):
    location, product, sale, invoice, sale_line, _ = setup_sale_fixture(
        db, client, initial_stock=15, sold_quantity=5
    )
    stock_before = db.scalar(
        select(StockLevel.quantity).where(
            StockLevel.product_id == product.id, StockLevel.location_id == location.id
        )
    )
    assert stock_before == 10

    # Return 1 damaged item
    resp_dam = client.post(
        "/api/sales/returns",
        json={
            "invoice_number": invoice.invoice_number,
            "lines": [
                {
                    "sale_line_id": sale_line.id,
                    "quantity": 1,
                    "condition": "damaged",
                }
            ],
            "reason": "Defective - screen cracked",
        },
    )
    assert resp_dam.status_code == 201, resp_dam.text
    data_dam = resp_dam.json()
    assert data_dam["non_sellable_quantity"] == 1
    assert data_dam["lines"][0]["condition"] == "damaged"
    assert data_dam["lines"][0]["restocked"] is False
    assert Decimal(data_dam["refund_total"]) > Decimal("0")

    stock_after_dam = db.scalar(
        select(StockLevel.quantity).where(
            StockLevel.product_id == product.id, StockLevel.location_id == location.id
        )
    )
    assert stock_after_dam == stock_before

    dam_movement = db.scalar(
        select(StockMovement).where(
            StockMovement.reference_type == "return",
            StockMovement.reference_id == data_dam["return_id"],
        )
    )
    assert dam_movement is None

    # Mixed return: 1 resaleable and 1 damaged
    resp_mix = client.post(
        "/api/sales/returns",
        json={
            "invoice_number": invoice.invoice_number,
            "lines": [
                {
                    "sale_line_id": sale_line.id,
                    "quantity": 1,
                    "condition": "resaleable",
                },
                {
                    "sale_line_id": sale_line.id,
                    "quantity": 1,
                    "condition": "damaged",
                },
            ],
            "reason": "Mixed condition return",
        },
    )
    assert resp_mix.status_code == 201, resp_mix.text
    data_mix = resp_mix.json()
    assert data_mix["non_sellable_quantity"] == 1

    stock_after_mix = db.scalar(
        select(StockLevel.quantity).where(
            StockLevel.product_id == product.id, StockLevel.location_id == location.id
        )
    )
    assert stock_after_mix == stock_before + 1


def test_fr4_2_it_2_late_return_manager_override_and_lockout(client, db, make_user):
    manager = make_user("manager_priya", role="manager")
    location, product, sale, invoice, sale_line, _ = setup_sale_fixture(
        db, client, backdate_days=35, sold_quantity=2
    )

    # Without approval -> 403 manager_approval_required
    resp_no_app = client.post(
        "/api/sales/returns",
        json={
            "invoice_number": invoice.invoice_number,
            "lines": [{"sale_line_id": sale_line.id, "quantity": 1, "condition": "resaleable"}],
            "reason": "Late return request",
        },
    )
    assert resp_no_app.status_code == 403
    assert "manager_approval_required" in resp_no_app.text
    assert db.scalar(select(func.count(Return.id))) == 0

    # Wrong manager credentials -> generic "Manager approval failed."
    resp_wrong_pw = client.post(
        "/api/sales/returns",
        json={
            "invoice_number": invoice.invoice_number,
            "lines": [{"sale_line_id": sale_line.id, "quantity": 1, "condition": "resaleable"}],
            "reason": "Late return request",
            "manager_approval": {"username": "manager_priya", "password": "wrong-password"},
        },
    )
    assert resp_wrong_pw.status_code == 403
    assert resp_wrong_pw.json()["detail"] == "Manager approval failed."

    # Cashier's own credentials -> generic "Manager approval failed."
    cashier_user = db.get(User, sale.cashier_id)
    assert cashier_user is not None
    resp_cashier_cred = client.post(
        "/api/sales/returns",
        json={
            "invoice_number": invoice.invoice_number,
            "lines": [{"sale_line_id": sale_line.id, "quantity": 1, "condition": "resaleable"}],
            "reason": "Late return request",
            "manager_approval": {"username": cashier_user.username, "password": PASSWORD},
        },
    )
    assert resp_cashier_cred.status_code == 403
    assert resp_cashier_cred.json()["detail"] == "Manager approval failed."

    # Lockout test: repeat wrong password until locked
    for _ in range(SETTINGS.lockout_threshold - 1):
        client.post(
            "/api/sales/returns",
            json={
                "invoice_number": invoice.invoice_number,
                "lines": [{"sale_line_id": sale_line.id, "quantity": 1, "condition": "resaleable"}],
                "reason": "Late return request",
                "manager_approval": {"username": "manager_priya", "password": "bad-password"},
            },
        )
    mgr_refreshed = db.get(User, manager.id)
    assert mgr_refreshed is not None
    assert mgr_refreshed.locked_until is not None

    # Reset lockout for next step
    mgr_refreshed.locked_until = None
    mgr_refreshed.failed_login_count = 0
    db.commit()

    # Correct Manager credentials -> 201
    resp_ok = client.post(
        "/api/sales/returns",
        json={
            "invoice_number": invoice.invoice_number,
            "lines": [{"sale_line_id": sale_line.id, "quantity": 1, "condition": "resaleable"}],
            "reason": "Late return approved",
            "manager_approval": {"username": "manager_priya", "password": PASSWORD},
        },
    )
    assert resp_ok.status_code == 201, resp_ok.text
    ret_data = resp_ok.json()
    assert ret_data["approver_username"] == "manager_priya"

    # Verify audit log recorded manager_priya as approver
    audit_entry = db.scalar(
        select(AuditLog)
        .where(
            AuditLog.entity_id == str(ret_data["return_id"]),
            AuditLog.action == "return_late_approved",
        )
        .order_by(AuditLog.id.desc())
    )
    assert audit_entry is not None
    assert "manager_priya" in audit_entry.details

    # Self-approval when processor is Manager
    login(client, "manager_priya")
    resp_self = client.post(
        "/api/sales/returns",
        json={
            "invoice_number": invoice.invoice_number,
            "lines": [{"sale_line_id": sale_line.id, "quantity": 1, "condition": "resaleable"}],
            "reason": "Manager self approved late return",
        },
    )
    assert resp_self.status_code == 201, resp_self.text
    ret_self_data = resp_self.json()
    assert ret_self_data["approver_username"] == "manager_priya"

    # Boundaries: 30 day old sale accepted without approval, 31 day old sale blocked
    _, _, sale_30, inv_30, sale_line_30, _ = setup_sale_fixture(
        db, client, backdate_days=30, sold_quantity=1
    )
    cashier_30 = db.get(User, sale_30.cashier_id)
    assert cashier_30 is not None
    login(client, cashier_30.username)
    resp_30 = client.post(
        "/api/sales/returns",
        json={
            "invoice_number": inv_30.invoice_number,
            "lines": [{"sale_line_id": sale_line_30.id, "quantity": 1, "condition": "resaleable"}],
            "reason": "Day 30 return",
        },
    )
    assert resp_30.status_code == 201, resp_30.text

    _, _, sale_31, inv_31, sale_line_31, _ = setup_sale_fixture(
        db, client, backdate_days=31, sold_quantity=1
    )
    cashier_31 = db.get(User, sale_31.cashier_id)
    assert cashier_31 is not None
    login(client, cashier_31.username)
    resp_31 = client.post(
        "/api/sales/returns",
        json={
            "invoice_number": inv_31.invoice_number,
            "lines": [{"sale_line_id": sale_line_31.id, "quantity": 1, "condition": "resaleable"}],
            "reason": "Day 31 return",
        },
    )
    assert resp_31.status_code == 403
    assert resp_31.json()["detail"]["code"] == "manager_approval_required"


def test_partial_returns_and_exact_refund_allocation(client, db, make_user):
    unit_price = Decimal("15000.00")
    location, product, sale, invoice, sale_line, _ = setup_sale_fixture(
        db, client, sold_quantity=3, unit_price=unit_price
    )
    expected_line_total = sale_line.line_total

    # Snapshot rows
    sale_snapshot = (sale.id, sale.total, sale.subtotal, sale.tax_total)
    line_snapshot = (sale_line.id, sale_line.quantity, sale_line.line_total)
    invoice_snapshot = (invoice.id, invoice.invoice_number, invoice.total)

    # Return 1 of 3
    r1 = client.post(
        "/api/sales/returns",
        json={
            "invoice_number": invoice.invoice_number,
            "lines": [{"sale_line_id": sale_line.id, "quantity": 1, "condition": "resaleable"}],
            "reason": "First partial return",
        },
    )
    assert r1.status_code == 201
    refund_1 = Decimal(r1.json()["refund_total"])

    # Check sale return_status
    sale_view = client.get(f"/api/sales/{sale.id}").json()
    assert sale_view["return_status"] == "partially_returned"

    # Return remaining 2 of 3
    r2 = client.post(
        "/api/sales/returns",
        json={
            "invoice_number": invoice.invoice_number,
            "lines": [{"sale_line_id": sale_line.id, "quantity": 2, "condition": "resaleable"}],
            "reason": "Second partial return",
        },
    )
    assert r2.status_code == 201
    refund_2 = Decimal(r2.json()["refund_total"])

    # Sum of refunds equals line total exactly
    assert refund_1 + refund_2 == expected_line_total

    sale_view_full = client.get(f"/api/sales/{sale.id}").json()
    assert sale_view_full["return_status"] == "fully_returned"

    # Attempt to return 1 more -> rejected with over-quantity message
    r3 = client.post(
        "/api/sales/returns",
        json={
            "invoice_number": invoice.invoice_number,
            "lines": [{"sale_line_id": sale_line.id, "quantity": 1, "condition": "resaleable"}],
            "reason": "Excess return attempt",
        },
    )
    assert r3.status_code == 422
    assert "exceeds returnable quantity" in r3.text

    # Verify original rows remain completely unchanged
    db.refresh(sale)
    db.refresh(sale_line)
    db.refresh(invoice)
    assert (sale.id, sale.total, sale.subtotal, sale.tax_total) == sale_snapshot
    assert (sale_line.id, sale_line.quantity, sale_line.line_total) == line_snapshot
    assert (invoice.id, invoice.invoice_number, invoice.total) == invoice_snapshot


def test_tracked_items_serial_and_batch_returns(client, db, make_user):
    # Serial tracking
    location, product, sale, invoice, sale_line, serials = setup_sale_fixture(
        db, client, tracking_mode="serial", sold_quantity=2
    )

    # Serial unit sold must be in 'sold' status
    sn1 = db.scalar(select(SerialNumber).where(SerialNumber.serial_number == serials[0]))
    assert sn1 is not None and sn1.status == "sold"

    # Missing serials -> 422
    r_bad_count = client.post(
        "/api/sales/returns",
        json={
            "invoice_number": invoice.invoice_number,
            "lines": [
                {
                    "sale_line_id": sale_line.id,
                    "quantity": 1,
                    "condition": "resaleable",
                    "serial_number_ids": [],
                }
            ],
            "reason": "Missing serial",
        },
    )
    assert r_bad_count.status_code == 422

    # Wrong serial not belonging to line -> 422
    r_wrong_sn = client.post(
        "/api/sales/returns",
        json={
            "invoice_number": invoice.invoice_number,
            "lines": [
                {
                    "sale_line_id": sale_line.id,
                    "quantity": 1,
                    "condition": "resaleable",
                    "serial_number_ids": [99999],
                }
            ],
            "reason": "Wrong serial",
        },
    )
    assert r_wrong_sn.status_code == 422

    # Return first serial
    r_sn = client.post(
        "/api/sales/returns",
        json={
            "invoice_number": invoice.invoice_number,
            "lines": [
                {
                    "sale_line_id": sale_line.id,
                    "quantity": 1,
                    "condition": "resaleable",
                    "serial_number_ids": [sn1.id],
                }
            ],
            "reason": "Valid serial return",
        },
    )
    assert r_sn.status_code == 201, r_sn.text
    db.refresh(sn1)
    assert sn1.status == "returned"

    # Batch tracking
    loc_b, prod_b, sale_b, inv_b, sale_line_b, _ = setup_sale_fixture(
        db, client, tracking_mode="batch", sold_quantity=3
    )
    r_batch = client.post(
        "/api/sales/returns",
        json={
            "invoice_number": inv_b.invoice_number,
            "lines": [{"sale_line_id": sale_line_b.id, "quantity": 2, "condition": "resaleable"}],
            "reason": "Valid batch return",
        },
    )
    assert r_batch.status_code == 201

    # Batch return quantity was tracked
    assert r_batch.json()["lines"][0]["restocked"] is True


def test_deleted_product_return_allowed_without_restock(client, db, make_user):
    location, product, sale, invoice, sale_line, _ = setup_sale_fixture(db, client, sold_quantity=2)

    # Deactivate product
    product.is_active = False
    db.commit()

    resp = client.post(
        "/api/sales/returns",
        json={
            "invoice_number": invoice.invoice_number,
            "lines": [{"sale_line_id": sale_line.id, "quantity": 1, "condition": "resaleable"}],
            "reason": "Product discontinued return",
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["lines"][0]["restocked"] is False
    assert Decimal(data["refund_total"]) > Decimal("0")


def test_authorization_and_location_scoping(client, db, make_user):
    loc_a = Location(name="Loc A", type="store")
    loc_b = Location(name="Loc B", type="store")
    db.add_all([loc_a, loc_b])
    db.flush()

    cashier_a = make_user("cashier_loc_a", role="cashier", location_id=loc_a.id)
    make_user("cashier_loc_b", role="cashier", location_id=loc_b.id)
    make_user("staff_member", role="staff", location_id=loc_a.id)
    make_user("manager_global", role="manager")

    _, _, sale_a, inv_a, sale_line_a, _ = setup_sale_fixture(
        db, client, location=loc_a, cashier=cashier_a, sold_quantity=2
    )

    # Cashier A can look up and return at Loc A
    login(client, "cashier_loc_a")
    assert client.get(f"/api/sales/by-invoice/{inv_a.invoice_number}").status_code == 200

    # Cashier B cannot look up or return Loc A's sale
    login(client, "cashier_loc_b")
    assert client.get(f"/api/sales/by-invoice/{inv_a.invoice_number}").status_code == 403
    r_denied = client.post(
        "/api/sales/returns",
        json={
            "invoice_number": inv_a.invoice_number,
            "lines": [{"sale_line_id": sale_line_a.id, "quantity": 1, "condition": "resaleable"}],
            "reason": "Unauthorized location return",
        },
    )
    assert r_denied.status_code == 403

    # Staff gets 403
    login(client, "staff_member")
    assert client.get(f"/api/sales/by-invoice/{inv_a.invoice_number}").status_code == 403

    # Manager can return Loc A's sale
    login(client, "manager_global")
    r_mgr = client.post(
        "/api/sales/returns",
        json={
            "invoice_number": inv_a.invoice_number,
            "lines": [{"sale_line_id": sale_line_a.id, "quantity": 1, "condition": "resaleable"}],
            "reason": "Manager cross location return",
        },
    )
    assert r_mgr.status_code == 201


def test_no_secrets_leaked_in_override_flow(client, db, make_user):
    secret_pass = "top-secret-password-xyz"
    mgr = make_user("secret_manager", role="manager")
    mgr.password_hash = hash_password(secret_pass)
    db.commit()

    location, product, sale, invoice, sale_line, _ = setup_sale_fixture(
        db, client, backdate_days=35, sold_quantity=2
    )

    resp = client.post(
        "/api/sales/returns",
        json={
            "invoice_number": invoice.invoice_number,
            "lines": [{"sale_line_id": sale_line.id, "quantity": 1, "condition": "resaleable"}],
            "reason": "Late return secret check",
            "manager_approval": {"username": "secret_manager", "password": secret_pass},
        },
    )
    assert resp.status_code == 201

    assert secret_pass not in resp.text

    audit_logs = db.scalars(select(AuditLog)).all()
    for log in audit_logs:
        assert secret_pass not in (log.details or "")
        if log.after:
            assert secret_pass not in str(log.after)


def test_fr4_2_st_1_end_to_end_sale_to_return(client, db, make_user):
    location, product, sale, invoice, sale_line, _ = setup_sale_fixture(
        db, client, initial_stock=20, sold_quantity=4, unit_price=Decimal("250.00")
    )

    lookup = client.get(f"/api/sales/by-invoice/{invoice.invoice_number}").json()
    assert lookup["invoice"]["invoice_number"] == invoice.invoice_number
    assert lookup["lines"][0]["quantity_returnable"] == 4
    assert lookup["return_status"] == "none"

    ret_resp = client.post(
        "/api/sales/returns",
        json={
            "invoice_number": invoice.invoice_number,
            "lines": [
                {
                    "sale_line_id": sale_line.id,
                    "quantity": 2,
                    "condition": "resaleable",
                }
            ],
            "reason": "E2E return test",
        },
    )
    assert ret_resp.status_code == 201
    ret_data = ret_resp.json()
    cn_number = ret_data["credit_note_number"]

    cn_resp = client.get(f"/api/sales/returns/{ret_data['return_id']}")
    assert cn_resp.status_code == 200
    assert cn_resp.json()["credit_note_number"] == cn_number

    sale_after = client.get(f"/api/sales/{sale.id}").json()
    assert sale_after["return_status"] == "partially_returned"


def test_fr4_2_it_3_net_sales_data_aggregatable(client, db, make_user):
    location, product, sale, invoice, sale_line, _ = setup_sale_fixture(
        db, client, sold_quantity=2, unit_price=Decimal("500.00")
    )

    client.post(
        "/api/sales/returns",
        json={
            "invoice_number": invoice.invoice_number,
            "lines": [
                {
                    "sale_line_id": sale_line.id,
                    "quantity": 1,
                    "condition": "resaleable",
                }
            ],
            "reason": "Net sales readiness check",
        },
    )

    # Query required by #31 to net sales by product
    results = db.execute(
        select(
            SaleLine.product_id,
            func.sum(ReturnLine.refund_amount).label("total_refunded"),
            func.count(Return.id).label("returns_count"),
        )
        .join(ReturnLine, ReturnLine.sale_line_id == SaleLine.id)
        .join(Return, Return.id == ReturnLine.return_id)
        .group_by(SaleLine.product_id)
    ).all()

    assert len(results) > 0
    prod_id, total_refunded, ret_count = results[0]
    assert prod_id == product.id
    assert total_refunded > Decimal("0")
    assert ret_count >= 1
