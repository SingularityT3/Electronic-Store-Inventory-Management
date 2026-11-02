"""Sales transaction recording (FR-4.1, FR-2.2, UC-13, Issue #24) and the stock it moves."""

from concurrent.futures import ThreadPoolExecutor
from decimal import ROUND_HALF_UP, Decimal
from threading import Barrier
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import URL, create_engine, func, select
from sqlalchemy.orm import Session

from app.modules.audit import audit_service
from app.modules.audit._internal.models import AuditLog
from app.modules.auth._internal.models import User
from app.modules.auth._internal.passwords import hash_password
from app.modules.product._internal.models import Category, Product, ProductVariant
from app.modules.purchasing._internal.models import (
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
)
from app.modules.sales._internal.models import Invoice, Sale, SaleLine
from app.modules.sales.service import (
    PaymentInput,
    SaleLineInput,
    SaleStockError,
    record_sale,
)
from app.modules.stock import receive_batch_stock, receive_serial_stock, update_stock
from app.modules.stock._internal.models import Location, SerialNumber, StockLevel, StockMovement
from tests.conftest import alembic_config
from tests.helpers import PASSWORD, SETTINGS, login

GST = Decimal("0.18")
CENT = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _location(db: Session, name: str | None = None, kind: str = "store") -> Location:
    location = Location(name=name or f"Store {uuid4().hex[:8]}", type=kind)
    db.add(location)
    db.flush()
    return location


def _product(
    db: Session,
    *,
    sku: str | None = None,
    price: str = "1000.00",
    tracking_mode: str = "untracked",
    name: str | None = None,
) -> Product:
    suffix = uuid4().hex[:8]
    category = Category(name=f"Sales category {suffix}")
    db.add(category)
    db.flush()
    product = Product(
        sku=sku or f"SKU-{suffix}",
        name=name or f"Sales product {suffix}",
        category_id=category.id,
        brand="Test",
        price=Decimal(price),
        tracking_mode=tracking_mode,
    )
    db.add(product)
    db.flush()
    return product


def _stock(
    db: Session, product: Product, location: Location, quantity: int, variant_id=None
) -> None:
    update_stock(
        db,
        product_id=product.id,
        variant_id=variant_id,
        location_id=location.id,
        quantity_delta=quantity,
        movement_type="receipt",
        record_audit=False,
    )


def _quantity(db: Session, product: Product, location: Location, variant_id=None) -> int | None:
    return db.scalar(
        select(StockLevel.quantity).where(
            StockLevel.product_id == product.id,
            StockLevel.variant_id.is_not_distinct_from(variant_id),
            StockLevel.location_id == location.id,
        )
    )


def _total(*lines: tuple[str, int]) -> Decimal:
    """Sale total for (unit price, quantity) lines: GST is added and rounded per line."""
    total = Decimal("0")
    for price, quantity in lines:
        gross = Decimal(price) * quantity
        total += gross + _money(gross * GST)
    return _money(total)


def _sell(client, location: Location, lines: list[dict], total: Decimal):
    return client.post(
        "/api/sales",
        json={
            "location_id": location.id,
            "lines": lines,
            "payments": [{"method": "cash", "amount": str(total)}],
        },
    )


def _sign_in(client, make_user, role: str, location: Location | None = None) -> User:
    username = f"sales_{role}_{uuid4().hex[:6]}"
    user = make_user(username, role=role, location_id=location.id if location else None)
    assert login(client, username).status_code == 200
    return user


def _counts(db: Session) -> tuple[int, int, int, int]:
    return (
        db.scalar(select(func.count(Sale.id))),
        db.scalar(select(func.count(SaleLine.id))),
        db.scalar(select(func.count(Invoice.id))),
        db.scalar(select(func.count(StockMovement.id))),
    )


def test_fr4_1_ut_1_cashier_records_a_sale_for_an_in_stock_product(client, make_user, db):
    location = _location(db)
    product = _product(db, sku=f"SKU-EL-{uuid4().hex[:6]}", price="30000.00")
    _stock(db, product, location, 20)
    db.commit()
    cashier = _sign_in(client, make_user, "cashier", location)

    response = _sell(
        client,
        location,
        [{"product_id": product.id, "quantity": 2}],
        _total(("30000.00", 2)),
    )

    assert response.status_code == 201, response.text
    sale = response.json()
    assert sale["cashier_id"] == cashier.id
    assert sale["location_id"] == location.id
    assert sale["lines"][0]["quantity"] == 2
    assert Decimal(sale["subtotal"]) == Decimal("60000.00")
    assert Decimal(sale["tax_total"]) == Decimal("10800.00")
    assert Decimal(sale["total"]) == Decimal("70800.00")
    assert sale["invoice"]["invoice_label"].startswith("INV-")
    assert db.scalar(
        select(AuditLog.id).where(
            AuditLog.action == "sale_recorded", AuditLog.entity_id == str(sale["id"])
        )
    )


def test_fr4_1_ut_2_and_fr2_2_ut_1_stock_drops_by_exactly_the_sold_quantity(client, make_user, db):
    location = _location(db, "Store-Chennai-01 test")
    product = _product(db, price="500.00")
    _stock(db, product, location, 70)
    db.commit()
    _sign_in(client, make_user, "cashier", location)

    first = _sell(client, location, [{"product_id": product.id, "quantity": 3}], _total(("500", 3)))
    assert first.status_code == 201, first.text
    assert _quantity(db, product, location) == 67

    second = _sell(
        client, location, [{"product_id": product.id, "quantity": 3}], _total(("500", 3))
    )
    assert second.status_code == 201, second.text
    assert _quantity(db, product, location) == 64
    movements = db.scalars(
        select(StockMovement.quantity_change).where(
            StockMovement.product_id == product.id, StockMovement.movement_type == "sale"
        )
    ).all()
    assert movements == [-3, -3]


def test_fr4_1_ut_3_zero_stock_is_out_of_stock_and_nothing_is_recorded(client, make_user, db):
    location = _location(db)
    product = _product(db)
    db.add(StockLevel(product_id=product.id, location_id=location.id, quantity=0))
    db.commit()
    _sign_in(client, make_user, "cashier", location)
    before = _counts(db)

    response = _sell(
        client, location, [{"product_id": product.id, "quantity": 1}], _total(("1000", 1))
    )

    assert response.status_code == 409
    assert response.json()["detail"][0]["message"] == "Out of stock"
    assert response.json()["detail"][0]["available"] == 0
    assert _counts(db) == before
    assert _quantity(db, product, location) == 0


def test_fr2_2_it_1_sale_above_available_stock_is_rejected_and_stock_unchanged(
    client, make_user, db
):
    location = _location(db)
    product = _product(db)
    _stock(db, product, location, 5)
    db.commit()
    _sign_in(client, make_user, "cashier", location)
    before = _counts(db)

    response = _sell(
        client, location, [{"product_id": product.id, "quantity": 10}], _total(("1000", 10))
    )

    assert response.status_code == 409
    assert response.json()["detail"] == [
        {"line": f"{product.id}:", "message": "Insufficient stock", "available": 5}
    ]
    assert _quantity(db, product, location) == 5
    assert _counts(db) == before


def test_fr4_1_it_1_multi_item_sale_deducts_each_item_and_totals_both(client, make_user, db):
    location = _location(db)
    phone = _product(db, price="25000.00")
    charger = _product(db, price="1500.00")
    _stock(db, phone, location, 15)
    _stock(db, charger, location, 60)
    db.commit()
    _sign_in(client, make_user, "cashier", location)

    total = _total(("25000.00", 2), ("1500.00", 5))
    response = _sell(
        client,
        location,
        [
            {"product_id": phone.id, "quantity": 2},
            {"product_id": charger.id, "quantity": 5},
        ],
        total,
    )

    assert response.status_code == 201, response.text
    assert _quantity(db, phone, location) == 13
    assert _quantity(db, charger, location) == 55
    sale = response.json()
    assert Decimal(sale["subtotal"]) == Decimal("57500.00")
    assert Decimal(sale["total"]) == total == Decimal("67850.00")
    assert sum(Decimal(line["line_total"]) for line in sale["lines"]) == total


def test_fr4_1_it_2_two_concurrent_sales_of_the_last_unit_sell_it_once(empty_db_url: URL):
    command.upgrade(alembic_config(empty_db_url), "head")
    engine = create_engine(empty_db_url, pool_size=4)
    try:
        with Session(engine) as setup:
            location = _location(setup, "Last unit store")
            product = _product(setup, price="100.00")
            cashiers = [
                User(
                    username=f"last_unit_{index}",
                    full_name=f"Last unit {index}",
                    password_hash=hash_password(PASSWORD),
                    role="cashier",
                    location_id=location.id,
                )
                for index in range(2)
            ]
            setup.add_all(cashiers)
            _stock(setup, product, location, 1)
            setup.commit()
            location_id, product_id = location.id, product.id
            cashier_ids = [(user.id, user.username) for user in cashiers]

        barrier = Barrier(2)

        def attempt(cashier: tuple[int, str]) -> str:
            with Session(engine) as session:
                barrier.wait()
                try:
                    record_sale(
                        session,
                        location_id=location_id,
                        cashier_id=cashier[0],
                        cashier_username=cashier[1],
                        lines=[SaleLineInput(product_id, None, 1, Decimal("0"), "amount", ())],
                        payments=[PaymentInput("cash", Decimal("118.00"), None)],
                        customer_name=None,
                        idempotency_key=None,
                        settings=SETTINGS,
                    )
                    session.commit()
                    return "sold"
                except SaleStockError as exc:
                    session.rollback()
                    return exc.errors[0]["message"]

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = sorted(pool.map(attempt, cashier_ids))

        assert outcomes[1] == "sold"
        assert outcomes[0] in {"Insufficient stock", "Out of stock"}
        with Session(engine) as check:
            assert (
                check.scalar(
                    select(StockLevel.quantity).where(
                        StockLevel.product_id == product_id, StockLevel.location_id == location_id
                    )
                )
                == 0
            )
            assert check.scalar(select(func.count(Sale.id))) == 1
    finally:
        engine.dispose()


def test_fr2_2_it_3_failure_after_stock_deduction_leaves_no_sale_invoice_or_stock_change(
    db, make_user, monkeypatch
):
    location = _location(db)
    product = _product(db, price="100.00")
    _stock(db, product, location, 25)
    db.commit()
    cashier = make_user(f"atomic_{uuid4().hex[:6]}", role="cashier", location_id=location.id)
    before = _counts(db)
    original = audit_service.record

    def interrupted(session, **kwargs):
        # The stock is already deducted and the invoice built when the sale is audited.
        if kwargs.get("action") == "sale_recorded":
            raise ConnectionError("simulated network interruption")
        return original(session, **kwargs)

    monkeypatch.setattr(audit_service, "record", interrupted)

    with pytest.raises(ConnectionError):
        try:
            record_sale(
                db,
                location_id=location.id,
                cashier_id=cashier.id,
                cashier_username=cashier.username,
                lines=[SaleLineInput(product.id, None, 5, Decimal("0"), "amount", ())],
                payments=[PaymentInput("cash", Decimal("590.00"), None)],
                customer_name=None,
                idempotency_key=None,
                settings=SETTINGS,
            )
        except Exception:
            db.rollback()
            raise

    assert _quantity(db, product, location) == 25
    assert _counts(db) == before


def _variant_product(db: Session) -> tuple[Product, ProductVariant, ProductVariant]:
    product = _product(db, price="30000.00", name=f"Smartphone X {uuid4().hex[:6]}")
    black = ProductVariant(
        product_id=product.id,
        sku=f"{product.sku}-BLK-128",
        attributes={"color": "Black", "storage": "128GB"},
        price=Decimal("32000.00"),
    )
    white = ProductVariant(
        product_id=product.id,
        sku=f"{product.sku}-WHT-256",
        attributes={"color": "White", "storage": "256GB"},
    )
    db.add_all([black, white])
    db.flush()
    return product, black, white


def test_fr1_3_it_2_selling_a_variant_deducts_only_that_variant(client, make_user, db):
    location = _location(db)
    product, black, white = _variant_product(db)
    _stock(db, product, location, 10, black.id)
    _stock(db, product, location, 5, white.id)
    db.commit()
    _sign_in(client, make_user, "cashier", location)

    response = _sell(
        client,
        location,
        [{"product_id": product.id, "variant_id": black.id, "quantity": 2}],
        _total(("32000.00", 2)),
    )

    assert response.status_code == 201, response.text
    assert _quantity(db, product, location, black.id) == 8
    assert _quantity(db, product, location, white.id) == 5


def test_fr1_3_st_1_cashier_sells_a_chosen_variant_at_its_price_and_invoice_shows_it(
    client, make_user, db
):
    location = _location(db)
    product, black, white = _variant_product(db)
    _stock(db, product, location, 10, black.id)
    _stock(db, product, location, 5, white.id)
    db.commit()
    _sign_in(client, make_user, "cashier", location)

    found = client.get("/api/product", params={"q": product.name})
    assert found.status_code == 200
    assert [item["id"] for item in found.json()["items"]] == [product.id]
    variants = client.get(f"/api/product/{product.id}/variants")
    assert variants.status_code == 200
    by_sku = {variant["sku"]: variant for variant in variants.json()}
    assert Decimal(by_sku[black.sku]["effective_price"]) == Decimal("32000.00")
    availability = client.get("/api/sales/availability", params={"ids": product.id})
    assert {(row["variant_id"], row["available_quantity"]) for row in availability.json()} == {
        (black.id, 10),
        (white.id, 5),
    }

    sale = _sell(
        client,
        location,
        [{"product_id": product.id, "variant_id": black.id, "quantity": 1}],
        _total(("32000.00", 1)),
    )

    assert sale.status_code == 201, sale.text
    line = sale.json()["lines"][0]
    assert (line["variant_id"], Decimal(line["unit_price"])) == (black.id, Decimal("32000.00"))
    invoice = client.get(f"/api/sales/invoices/{sale.json()['invoice']['invoice_number']}")
    assert invoice.status_code == 200
    invoice_line = invoice.json()["content"]["lines"][0]
    assert invoice_line["variant_sku"] == black.sku
    assert "Black" in invoice_line["variant_label"]
    assert invoice_line["unit_price"] == "32000.00"
    assert invoice.json()["content"]["total"] == "37760.00"
    assert _quantity(db, product, location, black.id) == 9
    assert _quantity(db, product, location, white.id) == 5


def test_fr4_1_st_1_search_to_sale_to_invoice_end_to_end(client, make_user, db):
    location = _location(db)
    sku = f"SKU-EL-{uuid4().hex[:6].upper()}"
    product = _product(db, sku=sku, price="2499.00")
    _stock(db, product, location, 12)
    db.commit()
    cashier = _sign_in(client, make_user, "cashier", location)

    search = client.get("/api/product", params={"q": sku.lower()})
    assert search.status_code == 200
    assert search.json()["items"][0]["id"] == product.id
    availability = client.get("/api/sales/availability", params={"ids": product.id})
    assert availability.json()[0]["available_quantity"] == 12

    total = _total(("2499.00", 1))
    sale = client.post(
        "/api/sales",
        json={
            "lines": [{"product_id": product.id, "quantity": 1}],
            "payments": [{"method": "card", "amount": str(total), "reference": "AUTH-1"}],
            "customer_name": "Walk-in customer",
        },
    )

    assert sale.status_code == 201, sale.text
    assert _quantity(db, product, location) == 11
    number = sale.json()["invoice"]["invoice_number"]
    invoice = client.get(f"/api/sales/invoices/{number}").json()["content"]
    assert invoice["cashier_id"] == cashier.id
    assert invoice["location_id"] == location.id
    assert invoice["customer_name"] == "Walk-in customer"
    assert invoice["lines"][0]["sku"] == sku
    assert invoice["total"] == f"{total:.2f}"
    assert invoice["payments"] == [
        {"method": "card", "amount": f"{total:.2f}", "reference": "AUTH-1"}
    ]
    history = client.get("/api/sales/history", params={"invoice": str(number)})
    assert history.status_code == 200
    assert number in [row["invoice_number"] for row in history.json()["items"]]


def test_fr4_1_st_2_staff_cannot_record_sales_but_cashier_and_manager_can(client, make_user, db):
    location = _location(db)
    product = _product(db, price="100.00")
    _stock(db, product, location, 10)
    db.commit()
    line = [{"product_id": product.id, "quantity": 1}]

    _sign_in(client, make_user, "staff", location)
    assert _sell(client, location, line, _total(("100", 1))).status_code == 403
    assert client.get("/api/sales/availability").status_code == 403
    assert _quantity(db, product, location) == 10

    for role in ("cashier", "manager"):
        client.post("/api/auth/logout")
        _sign_in(client, make_user, role, location if role == "cashier" else None)
        assert _sell(client, location, line, _total(("100", 1))).status_code == 201
    assert _quantity(db, product, location) == 8


def test_fr2_2_st_1_sale_receipt_and_transfer_cycle_keeps_both_locations_exact(
    client, make_user, db
):
    store_a = _location(db, f"Store-A {uuid4().hex[:6]}")
    store_b = _location(db, f"Store-B {uuid4().hex[:6]}")
    product = _product(db, price="100.00")
    _stock(db, product, store_a, 100)
    supplier = Supplier(name=f"Cycle supplier {uuid4().hex[:6]}")
    db.add(supplier)
    db.flush()
    manager = _sign_in(client, make_user, "manager")
    order = PurchaseOrder(
        po_number=f"PO-CYCLE-{uuid4().hex[:6]}",
        supplier_id=supplier.id,
        location_id=store_a.id,
        status="submitted",
        created_by=manager.id,
    )
    db.add(order)
    db.flush()
    po_line = PurchaseOrderLine(
        purchase_order_id=order.id,
        product_id=product.id,
        quantity_ordered=30,
        quantity_received=0,
        unit_price=Decimal("60.00"),
    )
    db.add(po_line)
    db.commit()

    sold = _sell(client, store_a, [{"product_id": product.id, "quantity": 10}], _total(("100", 10)))
    assert sold.status_code == 201, sold.text
    assert _quantity(db, product, store_a) == 90

    received = client.post(
        f"/api/purchasing/purchase-orders/{order.id}/receive",
        json={"lines": [{"po_line_id": po_line.id, "quantity_accepted": 30}]},
    )
    assert received.status_code == 200, received.text
    assert _quantity(db, product, store_a) == 120

    moved = client.post(
        "/api/stock/transfers",
        json={
            "product_id": product.id,
            "from_location_id": store_a.id,
            "to_location_id": store_b.id,
            "quantity": 15,
        },
    )
    assert moved.status_code == 201, moved.text

    assert _quantity(db, product, store_a) == 100 - 10 + 30 - 15 == 105
    assert _quantity(db, product, store_b) == 15
    movements = db.scalars(
        select(StockMovement.movement_type)
        .where(StockMovement.product_id == product.id)
        .order_by(StockMovement.id)
    ).all()
    assert movements == ["receipt", "sale", "receipt", "transfer_out", "transfer_in"]


def test_fr2_5_it_1_selling_a_serial_marks_only_that_unit_sold(client, make_user, db):
    location = _location(db)
    product = _product(db, price="40000.00", tracking_mode="serial")
    receiver = make_user(f"serial_receiver_{uuid4().hex[:6]}", role="manager")
    receive_serial_stock(
        db,
        product_id=product.id,
        variant_id=None,
        location_id=location.id,
        serial_numbers=["SN-TV-000123", "SN-TV-000124"],
        user_id=receiver.id,
        username=receiver.username,
        reference_type="po_receipt_line",
        reference_id=1,
    )
    db.commit()
    _sign_in(client, make_user, "cashier", location)

    sale = _sell(
        client,
        location,
        [{"product_id": product.id, "quantity": 1, "serial_numbers": ["SN-TV-000123"]}],
        _total(("40000.00", 1)),
    )

    assert sale.status_code == 201, sale.text
    statuses = dict(
        db.execute(
            select(SerialNumber.serial_number, SerialNumber.status).where(
                SerialNumber.product_id == product.id
            )
        ).all()
    )
    assert statuses == {"SN-TV-000123": "sold", "SN-TV-000124": "in_stock"}
    assert _quantity(db, product, location) == 1
    resold = _sell(
        client,
        location,
        [{"product_id": product.id, "quantity": 1, "serial_numbers": ["SN-TV-000123"]}],
        _total(("40000.00", 1)),
    )
    assert resold.status_code in {409, 422}


def _batch(
    db: Session, make_user, location: Location, quantity: int, number: str
) -> tuple[Product, int]:
    product = _product(db, price="1200.00", tracking_mode="batch", name="Power Bank 10000mAh")
    receiver = make_user(f"batch_receiver_{uuid4().hex[:6]}", role="manager")
    batch_id = receive_batch_stock(
        db,
        product_id=product.id,
        variant_id=None,
        location_id=location.id,
        batch_number=number,
        quantity=quantity,
        user_id=receiver.id,
        username=receiver.username,
        reference_type="po_receipt_line",
        reference_id=1,
    )
    return product, batch_id


def test_fr2_5_it_3_batch_lookup_by_number_splits_sold_and_in_stock_units(client, make_user, db):
    location = _location(db)
    number = f"BATCH-2026-08-{uuid4().hex[:4]}"
    product, batch_id = _batch(db, make_user, location, 100, number)
    db.commit()
    _sign_in(client, make_user, "cashier", location)
    sale = _sell(
        client, location, [{"product_id": product.id, "quantity": 40}], _total(("1200.00", 40))
    )
    assert sale.status_code == 201, sale.text
    invoice_number = sale.json()["invoice"]["invoice_number"]

    client.post("/api/auth/logout")
    _sign_in(client, make_user, "manager")
    lookup = client.get("/api/sales/batches/recall", params={"batch_number": number.lower()})

    assert lookup.status_code == 200, lookup.text
    [batch] = lookup.json()
    assert batch["batch_id"] == batch_id
    assert batch["batch_number"] == number
    assert (batch["product_name"], batch["sku"]) == (product.name, product.sku)
    assert batch["quantity_received"] == 100
    assert batch["quantity_in_stock"] == 60
    assert batch["locations"] == [
        {"location_id": location.id, "location_name": location.name, "quantity_in_stock": 60}
    ]
    assert batch["sold"] == [
        {
            "invoice_number": invoice_number,
            "invoice_label": sale.json()["invoice"]["invoice_label"],
            "quantity_sold": 40,
            "quantity_returned": 0,
            "quantity_still_sold": 40,
        }
    ]
    assert (
        client.get("/api/sales/batches/recall", params={"batch_number": "NO-SUCH"}).status_code
        == 404
    )


def test_batch_lookup_by_number_is_scoped_to_staff_location_and_denied_to_cashier(
    client, make_user, db
):
    home = _location(db)
    other = _location(db)
    number = f"BATCH-SCOPE-{uuid4().hex[:4]}"
    _batch(db, make_user, other, 5, number)
    db.commit()

    _sign_in(client, make_user, "staff", home)
    assert (
        client.get("/api/sales/batches/recall", params={"batch_number": number}).status_code == 404
    )
    client.post("/api/auth/logout")
    _sign_in(client, make_user, "staff", other)
    assert (
        client.get("/api/sales/batches/recall", params={"batch_number": number}).status_code == 200
    )
    client.post("/api/auth/logout")
    _sign_in(client, make_user, "cashier", other)
    assert (
        client.get("/api/sales/batches/recall", params={"batch_number": number}).status_code == 403
    )


def test_fr2_5_st_1_batch_received_on_a_po_is_traceable_through_sales_to_a_recall(
    client, make_user, db
):
    location = _location(db, kind="warehouse")
    product = _product(db, price="1200.00", tracking_mode="batch")
    supplier = Supplier(name=f"Recall supplier {uuid4().hex[:6]}")
    db.add(supplier)
    db.flush()
    admin = _sign_in(client, make_user, "admin")
    order = PurchaseOrder(
        po_number=f"PO-RECALL-{uuid4().hex[:6]}",
        supplier_id=supplier.id,
        location_id=location.id,
        status="submitted",
        created_by=admin.id,
    )
    db.add(order)
    db.flush()
    po_line = PurchaseOrderLine(
        purchase_order_id=order.id,
        product_id=product.id,
        quantity_ordered=20,
        quantity_received=0,
        unit_price=Decimal("800.00"),
    )
    db.add(po_line)
    db.commit()
    number = f"LOT-{uuid4().hex[:6]}"

    received = client.post(
        f"/api/purchasing/purchase-orders/{order.id}/receive",
        json={
            "lines": [{"po_line_id": po_line.id, "quantity_accepted": 20, "batch_number": number}]
        },
    )
    assert received.status_code == 200, received.text
    invoices = []
    for _ in range(5):
        sale = _sell(
            client, location, [{"product_id": product.id, "quantity": 1}], _total(("1200.00", 1))
        )
        assert sale.status_code == 201, sale.text
        invoices.append(sale.json()["invoice"]["invoice_number"])

    recall = client.get("/api/sales/batches/recall", params={"batch_number": number})

    assert recall.status_code == 200, recall.text
    [batch] = recall.json()
    assert batch["quantity_received"] == 20
    assert batch["quantity_in_stock"] == 15
    assert [row["invoice_number"] for row in batch["sold"]] == sorted(invoices)
    assert all(row["quantity_still_sold"] == 1 for row in batch["sold"])
    assert (
        batch["quantity_in_stock"] + sum(row["quantity_still_sold"] for row in batch["sold"]) == 20
    )
    [receipt] = batch["receipts"]
    assert receipt["reference_type"] == "po_receipt_line"
    assert receipt["quantity"] == 20
