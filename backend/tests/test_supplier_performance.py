"""Supplier performance report tests for Issue #33."""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth._internal.models import User
from app.modules.product._internal.models import Category, Product
from app.modules.purchasing._internal.models import (
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseOrderReceipt,
    PurchaseOrderReceiptLine,
    Supplier,
    SupplierPriceHistory,
)
from app.modules.stock._internal.models import Location
from tests.helpers import login


def create_supplier_product(
    db: Session, *, suffix: str | None = None
) -> tuple[Supplier, Product, Location]:
    suffix = suffix or uuid4().hex[:8]
    supplier = Supplier(name=f"Performance supplier {suffix}")
    location = Location(name=f"Performance location {suffix}", type="warehouse")
    category = Category(name=f"Performance category {suffix}")
    db.add_all([supplier, location, category])
    db.flush()
    product = Product(
        sku=f"PERF-{suffix}",
        name=f"Performance product {suffix}",
        category_id=category.id,
        brand="Test",
        price=Decimal("100.00"),
    )
    db.add(product)
    db.flush()
    return supplier, product, location


def add_order(
    db: Session,
    creator: User,
    supplier: Supplier,
    product: Product,
    location: Location,
    *,
    suffix: str,
    created_on: date,
    expected_on: date | None,
    ordered: int = 1,
    accepted: tuple[int, ...] = (),
    damaged: tuple[int, ...] = (),
    receipt_dates: tuple[datetime, ...] = (),
    unit_price: Decimal = Decimal("10.00"),
    status: str | None = None,
) -> PurchaseOrder:
    if len(accepted) != len(receipt_dates) or len(damaged) not in {0, len(receipt_dates)}:
        raise ValueError("Each receipt needs matching accepted and damaged quantities.")
    damaged = damaged or (0,) * len(receipt_dates)
    order = PurchaseOrder(
        po_number=f"PO-PERF-{suffix}",
        supplier_id=supplier.id,
        location_id=location.id,
        status=status or ("received" if sum(accepted) + sum(damaged) == ordered else "submitted"),
        created_by=creator.id,
        expected_delivery_date=expected_on,
        created_at=datetime.combine(created_on, time(hour=10), tzinfo=UTC),
    )
    db.add(order)
    db.flush()
    line = PurchaseOrderLine(
        purchase_order_id=order.id,
        product_id=product.id,
        quantity_ordered=ordered,
        quantity_received=sum(accepted) + sum(damaged),
        unit_price=unit_price,
    )
    db.add(line)
    db.flush()
    for received_at, quantity_accepted, quantity_damaged in zip(
        receipt_dates, accepted, damaged, strict=True
    ):
        receipt = PurchaseOrderReceipt(
            purchase_order_id=order.id,
            received_by=creator.id,
            received_at=received_at,
        )
        db.add(receipt)
        db.flush()
        db.add(
            PurchaseOrderReceiptLine(
                receipt_id=receipt.id,
                po_line_id=line.id,
                quantity_accepted=quantity_accepted,
                quantity_damaged=quantity_damaged,
                unit_price=unit_price,
            )
        )
    db.flush()
    return order


def report_url(date_from: date, date_to: date, *supplier_ids: int) -> str:
    url = f"/api/reporting/supplier-performance?date_from={date_from}&date_to={date_to}"
    return url + "".join(f"&supplier_ids={supplier_id}" for supplier_id in supplier_ids)


def test_supplier_performance_calculates_four_of_five_on_time_once_per_po(client, make_user, db):
    today = datetime.now(UTC).date()
    manager = make_user(f"performance_manager_{uuid4().hex[:6]}", role="manager")
    supplier, product, location = create_supplier_product(db)
    actual = datetime.combine(today - timedelta(days=4), time(hour=10), tzinfo=UTC)
    for index in range(5):
        on_time = index < 4
        expected = actual.date() if on_time else actual.date() - timedelta(days=1)
        receipts = (actual, actual + timedelta(days=1)) if index == 0 else (actual,)
        accepted = (1, 2) if index == 0 else (3,)
        add_order(
            db,
            manager,
            supplier,
            product,
            location,
            suffix=f"{index}-{uuid4().hex[:4]}",
            created_on=today - timedelta(days=10),
            expected_on=expected,
            ordered=3,
            accepted=accepted,
            receipt_dates=receipts,
        )
    db.commit()
    assert login(client, manager.username).status_code == 200

    response = client.get(report_url(today - timedelta(days=30), today, supplier.id))

    assert response.status_code == 200, response.text
    result = response.json()["suppliers"][0]
    assert result["purchase_order_count"] == 5
    assert result["eligible_delivery_count"] == 5
    assert result["on_time_delivery_count"] == 4
    assert Decimal(result["on_time_delivery_rate"]) == Decimal("80.00")
    assert result["quantity_ordered"] == 15
    assert result["quantity_accepted"] == 15


def test_supplier_performance_counts_orders_and_values_once_and_filters_by_period(
    client, make_user, db
):
    today = datetime.now(UTC).date()
    manager = make_user(f"performance_manager_{uuid4().hex[:6]}", role="manager")
    supplier, product, location = create_supplier_product(db)
    add_order(
        db,
        manager,
        supplier,
        product,
        location,
        suffix="value-a",
        created_on=today - timedelta(days=3),
        expected_on=None,
        ordered=3,
        accepted=(1, 1),
        receipt_dates=(
            datetime.combine(today - timedelta(days=2), time(10), tzinfo=UTC),
            datetime.combine(today - timedelta(days=1), time(10), tzinfo=UTC),
        ),
        unit_price=Decimal("10.00"),
    )
    add_order(
        db,
        manager,
        supplier,
        product,
        location,
        suffix="value-b",
        created_on=today - timedelta(days=2),
        expected_on=None,
        ordered=2,
        unit_price=Decimal("10.00"),
    )
    add_order(
        db,
        manager,
        supplier,
        product,
        location,
        suffix="outside",
        created_on=today - timedelta(days=8),
        expected_on=None,
        ordered=20,
        unit_price=Decimal("10.00"),
    )
    db.commit()
    assert login(client, manager.username).status_code == 200

    response = client.get(
        report_url(today - timedelta(days=4), today - timedelta(days=1), supplier.id)
    )

    assert response.status_code == 200, response.text
    result = response.json()["suppliers"][0]
    assert result["purchase_order_count"] == 2
    assert Decimal(result["total_order_value"]) == Decimal("50.00")
    assert result["eligible_delivery_count"] == 0
    assert result["quantity_ordered"] == 5
    assert result["quantity_accepted"] == 2
    assert Decimal(result["fulfilment_accuracy"]) == Decimal("40.00")


def test_supplier_performance_price_trends_match_supplier_and_product_history(
    client, make_user, db
):
    today = datetime.now(UTC).date()
    manager = make_user(f"performance_manager_{uuid4().hex[:6]}", role="manager")
    supplier, product, _location = create_supplier_product(db)
    other_supplier = Supplier(name=f"Other performance supplier {uuid4().hex[:8]}")
    db.add(other_supplier)
    db.flush()
    first_recorded = datetime.combine(today - timedelta(days=4), time(9), tzinfo=UTC)
    last_recorded = datetime.combine(today - timedelta(days=2), time(9), tzinfo=UTC)
    first = SupplierPriceHistory(
        supplier_id=supplier.id,
        product_id=product.id,
        unit_price=Decimal("100.00"),
        recorded_at=first_recorded,
    )
    db.add_all(
        [
            first,
            SupplierPriceHistory(
                supplier_id=supplier.id,
                product_id=product.id,
                unit_price=Decimal("120.00"),
                recorded_at=last_recorded,
            ),
            SupplierPriceHistory(
                supplier_id=other_supplier.id,
                product_id=product.id,
                unit_price=Decimal("300.00"),
                recorded_at=last_recorded,
            ),
            SupplierPriceHistory(
                supplier_id=supplier.id,
                product_id=product.id,
                unit_price=Decimal("80.00"),
                recorded_at=datetime.combine(today - timedelta(days=40), time(9), tzinfo=UTC),
            ),
        ]
    )
    db.commit()
    initial_values = db.scalar(
        select(SupplierPriceHistory.unit_price).where(SupplierPriceHistory.id == first.id)
    )
    assert login(client, manager.username).status_code == 200

    response = client.get(
        report_url(today - timedelta(days=10), today, supplier.id, other_supplier.id)
    )

    assert response.status_code == 200, response.text
    suppliers = {item["supplier_id"]: item for item in response.json()["suppliers"]}
    first_trend = suppliers[supplier.id]["price_trends"][0]
    other_trend = suppliers[other_supplier.id]["price_trends"][0]
    assert first_trend["product_id"] == product.id
    assert first_trend["product_name"] == product.name
    assert first_trend["sku"] == product.sku
    assert [point["unit_price"] for point in first_trend["price_points"]] == [
        "100.00",
        "120.00",
    ]
    assert first_trend["variance"] == "20.00"
    assert first_trend["variance_percent"] == "20.00"
    assert [point["unit_price"] for point in other_trend["price_points"]] == ["300.00"]
    db.refresh(first)
    assert first.unit_price == initial_values == Decimal("100.00")
    assert first.recorded_at == first_recorded


def test_supplier_performance_uses_only_accepted_receipts_and_reflects_receipt_updates(
    client, make_user, db
):
    today = datetime.now(UTC).date()
    manager = make_user(f"performance_manager_{uuid4().hex[:6]}", role="manager")
    supplier, product, location = create_supplier_product(db)
    order = PurchaseOrder(
        po_number=f"PO-PERF-INTEGRATION-{uuid4().hex[:6]}",
        supplier_id=supplier.id,
        location_id=location.id,
        status="submitted",
        created_by=manager.id,
        expected_delivery_date=today,
        created_at=datetime.combine(today - timedelta(days=2), time(10), tzinfo=UTC),
    )
    db.add(order)
    db.flush()
    line = PurchaseOrderLine(
        purchase_order_id=order.id,
        product_id=product.id,
        quantity_ordered=4,
        quantity_received=0,
        unit_price=Decimal("10.00"),
    )
    db.add(line)
    db.commit()
    assert login(client, manager.username).status_code == 200

    first_receipt = client.post(
        f"/api/purchasing/purchase-orders/{order.id}/receive",
        json={
            "lines": [
                {
                    "po_line_id": line.id,
                    "quantity_accepted": 2,
                    "quantity_damaged": 1,
                    "quantity_short": 1,
                    "unit_price": "10.00",
                    "discrepancy_note": "Damaged and short units",
                }
            ]
        },
    )
    assert first_receipt.status_code == 200, first_receipt.text
    first_report = client.get(report_url(today - timedelta(days=5), today, supplier.id))
    assert first_report.status_code == 200, first_report.text
    first_metrics = first_report.json()["suppliers"][0]
    assert first_metrics["eligible_delivery_count"] == 1
    assert first_metrics["on_time_delivery_count"] == 1
    assert first_metrics["quantity_ordered"] == 4
    assert first_metrics["quantity_accepted"] == 2
    assert Decimal(first_metrics["fulfilment_accuracy"]) == Decimal("50.00")

    second_receipt = client.post(
        f"/api/purchasing/purchase-orders/{order.id}/receive",
        json={
            "lines": [
                {
                    "po_line_id": line.id,
                    "quantity_accepted": 1,
                    "unit_price": "10.00",
                }
            ]
        },
    )
    assert second_receipt.status_code == 200, second_receipt.text
    updated = client.get(report_url(today - timedelta(days=5), today, supplier.id))
    assert updated.status_code == 200, updated.text
    metrics = updated.json()["suppliers"][0]
    assert metrics["eligible_delivery_count"] == 1
    assert metrics["on_time_delivery_count"] == 1
    assert metrics["quantity_accepted"] == 3
    assert Decimal(metrics["fulfilment_accuracy"]) == Decimal("75.00")


def test_supplier_performance_handles_missing_dates_and_empty_supplier_data(client, make_user, db):
    today = datetime.now(UTC).date()
    manager = make_user(f"performance_manager_{uuid4().hex[:6]}", role="manager")
    supplier, product, location = create_supplier_product(db)
    add_order(
        db,
        manager,
        supplier,
        product,
        location,
        suffix="no-expected",
        created_on=today - timedelta(days=2),
        expected_on=None,
        accepted=(1,),
        receipt_dates=(datetime.combine(today - timedelta(days=1), time(10), tzinfo=UTC),),
    )
    add_order(
        db,
        manager,
        supplier,
        product,
        location,
        suffix="no-actual",
        created_on=today - timedelta(days=1),
        expected_on=today,
    )
    db.commit()
    assert login(client, manager.username).status_code == 200

    response = client.get(report_url(today - timedelta(days=5), today, supplier.id))
    assert response.status_code == 200, response.text
    metrics = response.json()["suppliers"][0]
    assert metrics["purchase_order_count"] == 2
    assert metrics["on_time_delivery_rate"] is None
    assert metrics["eligible_delivery_count"] == 0
    assert metrics["fulfilment_accuracy"] == "50.00"
    assert metrics["price_trends"] == []

    no_suppliers = client.get(
        f"/api/reporting/supplier-performance?date_from={today - timedelta(days=1)}&date_to={today}"
    )
    assert no_suppliers.status_code == 200, no_suppliers.text
    assert len(no_suppliers.json()["suppliers"]) == 1
    assert no_suppliers.json()["suppliers"][0]["purchase_order_count"] == 1


def test_supplier_performance_returns_empty_list_when_there_are_no_suppliers(client, make_user):
    today = datetime.now(UTC).date()
    manager = make_user(f"performance_manager_{uuid4().hex[:6]}", role="manager")
    assert login(client, manager.username).status_code == 200

    response = client.get(
        f"/api/reporting/supplier-performance?date_from={today - timedelta(days=1)}&date_to={today}"
    )

    assert response.status_code == 200, response.text
    assert response.json()["suppliers"] == []


def test_supplier_performance_date_validation_and_manager_admin_access(client, make_user, db):
    today = datetime.now(UTC).date()
    _supplier, _product, location = create_supplier_product(db)
    endpoint = report_url(today - timedelta(days=1), today)
    manager_name = f"performance_manager_{uuid4().hex[:6]}"
    make_user(manager_name, role="manager")
    assert login(client, manager_name).status_code == 200
    invalid_range_url = (
        f"/api/reporting/supplier-performance?date_from={today}&"
        f"date_to={today - timedelta(days=1)}"
    )
    future_range_url = (
        f"/api/reporting/supplier-performance?date_from={today}&"
        f"date_to={today + timedelta(days=1)}"
    )
    assert client.get(invalid_range_url).status_code == 422
    assert client.get(future_range_url).status_code == 422
    assert client.get(endpoint).status_code == 200

    for role in ("admin", "staff", "cashier"):
        client.post("/api/auth/logout")
        username = f"performance_{role}_{uuid4().hex[:6]}"
        fields = {"location_id": location.id} if role in {"staff", "cashier"} else {}
        make_user(username, role=role, **fields)
        assert login(client, username).status_code == 200
        response = client.get(endpoint)
        assert response.status_code == (200 if role == "admin" else 403)
