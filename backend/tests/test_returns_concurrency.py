"""Concurrency and atomicity tests for returns (NFR-15, Issue #25)."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import URL, create_engine, func, select
from sqlalchemy.orm import Session

from app.modules.audit import audit_service
from app.modules.auth._internal.models import User
from app.modules.auth._internal.passwords import hash_password
from app.modules.product._internal.models import Category, Product
from app.modules.sales import (
    ReturnLineInput,
    SaleInputError,
    process_return,
)
from app.modules.sales._internal.models import (
    Invoice,
    Return,
    SaleLine,
)
from app.modules.sales.service import PaymentInput, SaleLineInput, record_sale
from app.modules.stock import update_stock
from app.modules.stock._internal.models import Location, StockLevel, StockMovement
from tests.conftest import alembic_config
from tests.helpers import PASSWORD, SETTINGS


def test_concurrent_returns_of_last_returnable_unit(empty_db_url: URL):
    command.upgrade(alembic_config(empty_db_url), "head")
    engine = create_engine(empty_db_url, pool_size=5)

    with Session(engine) as session:
        suffix = uuid4().hex[:8]
        loc = Location(name=f"Loc {suffix}", type="store")
        cat = Category(name=f"Cat {suffix}")
        session.add_all([loc, cat])
        session.flush()

        product = Product(
            sku=f"SKU-{suffix}",
            name=f"Prod {suffix}",
            category_id=cat.id,
            brand="Brand",
            price=Decimal("100.00"),
        )
        cashier = User(
            username=f"cashier_{suffix}",
            full_name="Cashier",
            password_hash=hash_password(PASSWORD),
            role="cashier",
            location_id=loc.id,
        )
        session.add_all([product, cashier])
        session.flush()

        update_stock(
            session,
            product_id=product.id,
            variant_id=None,
            location_id=loc.id,
            quantity_delta=10,
            movement_type="receipt",
            user_id=cashier.id,
            username=cashier.username,
            record_audit=False,
        )

        sale = record_sale(
            session,
            location_id=loc.id,
            cashier_id=cashier.id,
            cashier_username=cashier.username,
            lines=[SaleLineInput(product.id, None, 1, Decimal("0"), "amount", ())],
            payments=[PaymentInput("cash", Decimal("118.00"), None)],
            customer_name=None,
            idempotency_key=None,
            settings=SETTINGS,
        )
        session.commit()

        invoice = session.scalar(select(Invoice).where(Invoice.sale_id == sale.id))
        assert invoice is not None
        sale_line = session.scalar(select(SaleLine).where(SaleLine.sale_id == sale.id))
        assert sale_line is not None
        invoice_number = invoice.invoice_number
        sale_line_id = sale_line.id
        location_id = loc.id
        product_id = product.id
        cashier_id = cashier.id
        cashier_username = cashier.username

    barrier = Barrier(2)
    results: list[dict[str, object]] = []

    def perform_return() -> dict[str, object]:
        barrier.wait()
        with Session(engine) as worker_session:
            try:
                credit_note = process_return(
                    worker_session,
                    invoice_number_raw=invoice_number,
                    lines=[
                        ReturnLineInput(
                            sale_line_id=sale_line_id,
                            quantity=1,
                            condition="resaleable",
                        )
                    ],
                    reason="Concurrent return attempt",
                    processor_id=cashier_id,
                    processor_username=cashier_username,
                    processor_role="cashier",
                    settings=SETTINGS,
                )
                worker_session.commit()
                return {"success": True, "credit_note": credit_note.credit_note_number}
            except SaleInputError as exc:
                worker_session.rollback()
                return {"success": False, "error": str(exc.errors)}
            except Exception as exc:
                worker_session.rollback()
                return {"success": False, "error": str(exc)}

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(perform_return), pool.submit(perform_return)]
        results = [f.result() for f in futures]

    successes = [r for r in results if r["success"]]
    failures = [r for r in results if not r["success"]]

    assert len(successes) == 1, f"Expected 1 success, got: {results}"
    assert len(failures) == 1, f"Expected 1 failure, got: {results}"
    assert "exceeds returnable quantity" in str(failures[0]["error"])

    # Stock was 9 after sale of 1 from 10; after 1 return it should be exactly 10
    with Session(engine) as check_session:
        final_stock = check_session.scalar(
            select(StockLevel.quantity).where(
                StockLevel.product_id == product_id, StockLevel.location_id == location_id
            )
        )
        assert final_stock == 10
        total_returns = check_session.scalar(select(func.count(Return.id)))
        assert total_returns == 1


def test_atomicity_failure_mid_return_rolls_back_everything(db: Session, make_user, monkeypatch):
    suffix = uuid4().hex[:8]
    loc = Location(name=f"AtomLoc {suffix}", type="store")
    cat = Category(name=f"AtomCat {suffix}")
    db.add_all([loc, cat])
    db.flush()

    product = Product(
        sku=f"SKU-{suffix}",
        name=f"AtomProd {suffix}",
        category_id=cat.id,
        brand="Brand",
        price=Decimal("100.00"),
    )
    cashier = make_user(f"cashier_atom_{suffix}", role="cashier", location_id=loc.id)
    db.add(product)
    db.flush()

    update_stock(
        db,
        product_id=product.id,
        variant_id=None,
        location_id=loc.id,
        quantity_delta=10,
        movement_type="receipt",
        user_id=cashier.id,
        username=cashier.username,
        record_audit=False,
    )

    sale = record_sale(
        db,
        location_id=loc.id,
        cashier_id=cashier.id,
        cashier_username=cashier.username,
        lines=[SaleLineInput(product.id, None, 2, Decimal("0"), "amount", ())],
        payments=[PaymentInput("cash", Decimal("236.00"), None)],
        customer_name=None,
        idempotency_key=None,
        settings=SETTINGS,
    )
    db.commit()

    invoice = db.scalar(select(Invoice).where(Invoice.sale_id == sale.id))
    assert invoice is not None
    sale_line = db.scalar(select(SaleLine).where(SaleLine.sale_id == sale.id))
    assert sale_line is not None
    stock_before = db.scalar(
        select(StockLevel.quantity).where(
            StockLevel.product_id == product.id, StockLevel.location_id == loc.id
        )
    )
    assert stock_before == 8
    movements_before = db.scalar(select(func.count(StockMovement.id)))
    returns_before = db.scalar(select(func.count(Return.id)))

    # Monkeypatch audit_service.record to fail when action == "return_processed"
    orig_record = audit_service.record

    def fail_audit(db_session, **kwargs):
        if kwargs.get("action") == "return_processed":
            raise RuntimeError("simulated audit failure after stock restore")
        return orig_record(db_session, **kwargs)

    monkeypatch.setattr(audit_service, "record", fail_audit)

    with pytest.raises(RuntimeError, match="simulated audit failure"):
        try:
            process_return(
                db,
                invoice_number_raw=invoice.invoice_number,
                lines=[
                    ReturnLineInput(
                        sale_line_id=sale_line.id,
                        quantity=1,
                        condition="resaleable",
                    )
                ],
                reason="Atomicity test",
                processor_id=cashier.id,
                processor_username=cashier.username,
                processor_role="cashier",
                settings=SETTINGS,
            )
        except Exception:
            db.rollback()
            raise

    # Verify everything rolled back
    stock_after = db.scalar(
        select(StockLevel.quantity).where(
            StockLevel.product_id == product.id, StockLevel.location_id == loc.id
        )
    )
    assert stock_after == stock_before
    movements_after = db.scalar(select(func.count(StockMovement.id)))
    assert movements_after == movements_before
    returns_after = db.scalar(select(func.count(Return.id)))
    assert returns_after == returns_before
