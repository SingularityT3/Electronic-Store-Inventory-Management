"""Invoice snapshots, history and document exports (FR-4.3, UC-15, Issue #26)."""

import re
import zlib
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import URL, create_engine, func, select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.modules.audit._internal.models import AuditLog
from app.modules.auth._internal.models import User
from app.modules.auth._internal.passwords import hash_password
from app.modules.product._internal.models import Category, Product
from app.modules.sales._internal.models import Invoice, Return
from app.modules.sales.service import PaymentInput, SaleLineInput, record_sale
from app.modules.stock import update_stock
from app.modules.stock._internal.models import Location
from tests.conftest import alembic_config
from tests.helpers import PASSWORD, SETTINGS, login
from tests.test_returns import setup_sale_fixture


def _pdf_text(content: bytes) -> str:
    streams = re.findall(rb"stream\r?\n(.*?)\r?\nendstream", content, re.S)
    return " ".join(
        zlib.decompress(stream).decode("latin-1") for stream in streams if stream[:1] == b"x"
    )


def test_fr4_3_ut_1_invoice_snapshot_is_available_with_the_sale(client, db):
    _location, _product, sale, invoice, _line, _serials = setup_sale_fixture(db, client)
    sale_response = client.get(f"/api/sales/{sale.id}")
    assert sale_response.status_code == 200
    assert sale_response.json()["invoice"]["invoice_label"] == f"INV-{invoice.invoice_number:04d}"

    response = client.get(f"/api/sales/invoices/{invoice.invoice_number}")
    assert response.status_code == 200
    content = response.json()["content"]
    assert content["invoice_label"] == f"INV-{invoice.invoice_number:04d}"
    assert content["total"] == f"{sale.total:.2f}"
    assert content["lines"][0]["quantity"] == sale_response.json()["lines"][0]["quantity"]
    _l2, _p2, _s2, invoice2, _line2, _serials2 = setup_sale_fixture(db, client)
    assert invoice2.invoice_number != invoice.invoice_number


def test_fr4_3_ut_2_sale_persists_required_invoice_snapshot(client, db):
    _location, product, sale, invoice, _line, _serials = setup_sale_fixture(
        db, client, unit_price=Decimal("30000.00"), sold_quantity=1
    )
    content = invoice.content
    assert content["version"] == 1
    assert content["kind"] == "invoice"
    assert content["invoice_label"] == f"INV-{invoice.invoice_number:04d}"
    assert content["cashier_id"] == sale.cashier_id
    assert content["cashier_name"]
    assert content["location_name"]
    assert content["store_name"]
    assert Decimal(content["gst_rate"]) == Decimal("18.00")
    assert content["lines"][0]["product_name"] == product.name
    assert content["lines"][0]["sku"] == product.sku
    assert Decimal(content["tax_total"]) == Decimal("5400.00")
    assert Decimal(content["total"]) == Decimal("35400.00")
    assert Decimal(content["payments"][0]["amount"]) == Decimal("35400.00")


def test_fr4_3_st_2_invoice_pdf_has_attachment_headers_and_snapshot_text(client, db):
    _location, product, _sale, invoice, line, _serials = setup_sale_fixture(
        db, client, unit_price=Decimal("30000.00"), sold_quantity=1
    )
    response = client.get(f"/api/sales/invoices/{invoice.invoice_number}/pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-disposition"] == (
        f'attachment; filename="invoice-INV-{invoice.invoice_number:04d}.pdf"'
    )
    assert response.content.startswith(b"%PDF-")
    text = _pdf_text(response.content)
    assert f"INV-{invoice.invoice_number:04d}" in text
    assert product.name in text
    assert "30000.00" in text
    assert "5400.00" in text
    assert "35400.00" in text
    assert str(line.quantity) in text
    assert (
        db.scalar(select(func.count(AuditLog.id)).where(AuditLog.action == "invoice_pdf_exported"))
        == 1
    )


def test_pdf_renderer_failure_is_clean_and_not_audited(client, db, monkeypatch):
    _location, _product, _sale, invoice, _line, _serials = setup_sale_fixture(db, client)

    def fail_renderer(_document):
        raise RuntimeError("renderer failed")

    monkeypatch.setattr("app.modules.sales.router.document_pdf", fail_renderer)
    response = client.get(f"/api/sales/invoices/{invoice.invoice_number}/pdf")
    assert response.status_code == 500
    assert response.json()["detail"] == (
        "Could not generate the PDF. You can try again or view the invoice on screen."
    )
    assert (
        db.scalar(select(func.count(AuditLog.id)).where(AuditLog.action == "invoice_pdf_exported"))
        == 0
    )


def test_invoice_routes_deny_staff_and_signed_out_users(client, db, make_user):
    location, _product, _sale, invoice, _line, _serials = setup_sale_fixture(db, client)
    staff = make_user("invoice_staff", role="staff", location_id=location.id)
    assert login(client, staff.username).status_code == 200
    assert client.get(f"/api/sales/invoices/{invoice.invoice_number}").status_code == 403
    client.cookies.clear()
    assert client.get(f"/api/sales/invoices/{invoice.invoice_number}").status_code == 401


def test_fr4_3_it_1_invoice_row_rejects_updates(client, db):
    _location, _product, _sale, invoice, _line, _serials = setup_sale_fixture(db, client)
    with pytest.raises(ProgrammingError, match="append-only"), db.begin_nested():
        db.execute(
            text("UPDATE invoices SET total = total WHERE id = :invoice_id"),
            {"invoice_id": invoice.id},
        )
    assert db.scalar(select(Invoice.id).where(Invoice.id == invoice.id)) == invoice.id


def test_fr4_3_it_3_history_finds_a_seven_year_old_sale_by_date_and_number(client, db):
    _location, _product, sale, invoice, _line, _serials = setup_sale_fixture(
        db, client, backdate_days=365 * 7
    )
    params = {
        "date_from": sale.sold_at.date().isoformat(),
        "date_to": sale.sold_at.date().isoformat(),
        "invoice": f"INV-{invoice.invoice_number:04d}",
    }
    assert client.get("/api/sales/history").json()["total"] == 1
    by_date = client.get(
        "/api/sales/history",
        params={"date_from": params["date_from"], "date_to": params["date_to"]},
    )
    assert by_date.status_code == 200, by_date.text
    assert by_date.json()["total"] == 1
    response = client.get("/api/sales/history", params={"invoice": params["invoice"]})
    assert response.json()["items"][0]["invoice_label"] == f"INV-{invoice.invoice_number:04d}"
    params["invoice"] = str(invoice.invoice_number)
    assert client.get("/api/sales/history", params=params).json()["total"] == 1


def test_credit_note_snapshot_survives_product_rename_and_is_immutable(client, db):
    _location, product, _sale, invoice, line, _serials = setup_sale_fixture(
        db, client, sold_quantity=2
    )
    response = client.post(
        "/api/sales/returns",
        json={
            "invoice_number": f"INV-{invoice.invoice_number:04d}",
            "lines": [{"sale_line_id": line.id, "quantity": 1, "condition": "resaleable"}],
            "reason": "Changed mind",
        },
    )
    assert response.status_code == 201, response.text
    return_id = response.json()["return_id"]
    saved_name = response.json()["content"]["lines"][0]["product_name"]
    product.name = "Renamed after return"
    db.commit()

    reread = client.get(f"/api/sales/returns/{return_id}")
    assert reread.status_code == 200
    assert reread.json()["content"]["lines"][0]["product_name"] == saved_name
    pdf_response = client.get(f"/api/sales/returns/{return_id}/pdf")
    assert pdf_response.status_code == 200
    assert pdf_response.headers["content-type"] == "application/pdf"
    assert pdf_response.headers["content-disposition"].endswith(
        f'filename="credit-note-CN-{return_id:04d}.pdf"'
    )
    return_row = db.get(Return, return_id)
    assert return_row is not None
    with pytest.raises(ProgrammingError, match="immutable"), db.begin_nested():
        db.execute(
            text("UPDATE returns SET content = '{}'::jsonb WHERE id = :return_id"),
            {"return_id": return_id},
        )


def test_fr4_3_st_1_twenty_parallel_cashiers_get_distinct_invoice_numbers(
    empty_db_url: URL,
):
    command.upgrade(alembic_config(empty_db_url), "head")
    engine = create_engine(empty_db_url, pool_size=20)
    suffix = uuid4().hex[:8]
    with Session(engine) as session:
        location = Location(name=f"Parallel Store {suffix}", type="store")
        category = Category(name=f"Parallel Category {suffix}")
        session.add_all([location, category])
        session.flush()
        product = Product(
            sku=f"PAR-{suffix}",
            name="Parallel sale item",
            category_id=category.id,
            brand="Test",
            price=Decimal("100.00"),
        )
        session.add(product)
        session.flush()
        password_hash = hash_password(PASSWORD)
        cashiers = [
            User(
                username=f"parallel_{suffix}_{index}",
                full_name=f"Cashier {index}",
                password_hash=password_hash,
                role="cashier",
                location_id=location.id,
            )
            for index in range(20)
        ]
        session.add_all(cashiers)
        session.flush()
        update_stock(
            session,
            product_id=product.id,
            variant_id=None,
            location_id=location.id,
            quantity_delta=20,
            movement_type="receipt",
            user_id=cashiers[0].id,
            username=cashiers[0].username,
            record_audit=False,
        )
        session.commit()
        cashier_ids = [user.id for user in cashiers]
        cashier_names = [user.username for user in cashiers]
        product_id = product.id
        location_id = location.id

    barrier = Barrier(20)

    def record_for(cashier_id: int, username: str) -> int:
        barrier.wait()
        with Session(engine) as session:
            sale = record_sale(
                session,
                location_id=location_id,
                cashier_id=cashier_id,
                cashier_username=username,
                lines=[SaleLineInput(product_id, None, 1, Decimal("0"), "amount")],
                payments=[PaymentInput("cash", Decimal("118.00"), None)],
                customer_name=None,
                idempotency_key=None,
                settings=SETTINGS,
            )
            invoice = session.scalar(select(Invoice).where(Invoice.sale_id == sale.id))
            assert invoice is not None
            number = invoice.invoice_number
            session.commit()
            return number

    with ThreadPoolExecutor(max_workers=20) as pool:
        numbers = list(pool.map(record_for, cashier_ids, cashier_names))
    assert len(numbers) == 20
    assert len(set(numbers)) == 20
    with Session(engine) as session:
        assert session.scalar(select(func.count(Invoice.id))) == 20
        assert (
            session.scalar(
                select(func.count(Invoice.id)).where(Invoice.invoice_number.in_(numbers))
            )
            == 20
        )
    engine.dispose()
