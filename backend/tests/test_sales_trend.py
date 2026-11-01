from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.modules.product._internal.models import Category, Product
from app.modules.sales._internal.models import Return, ReturnLine, Sale, SaleLine
from app.modules.stock._internal.models import Location, StockLevel
from tests.helpers import login


def _seed_report(db, user_id: int):
    location = Location(name="Trend Store", type="store")
    category = Category(name="Trend Category")
    db.add_all([location, category])
    db.flush()
    products = [
        Product(
            sku=f"TREND-{index}",
            name=f"Trend Product {index}",
            category_id=category.id,
            brand="Trend",
            price=Decimal("10"),
        )
        for index in range(3)
    ]
    db.add_all(products)
    db.flush()
    db.add_all(
        [
            StockLevel(product_id=products[0].id, location_id=location.id, quantity=7),
            StockLevel(product_id=products[1].id, location_id=location.id, quantity=2),
            StockLevel(product_id=products[2].id, location_id=location.id, quantity=0),
        ]
    )
    sold_at = datetime.now(UTC) - timedelta(days=2)
    sale = Sale(
        location_id=location.id,
        cashier_id=user_id,
        subtotal=Decimal("50"),
        total=Decimal("50"),
        sold_at=sold_at,
    )
    db.add(sale)
    db.flush()
    lines = [
        SaleLine(
            sale_id=sale.id,
            product_id=products[0].id,
            quantity=5,
            unit_price=Decimal("10"),
            line_total=Decimal("50"),
        ),
    ]
    db.add_all(lines)
    db.flush()
    returned = Return(
        sale_id=sale.id,
        processed_by=user_id,
        refund_total=Decimal("20"),
    )
    db.add(returned)
    db.flush()
    db.add(
        ReturnLine(
            return_id=returned.id,
            sale_line_id=lines[0].id,
            quantity=2,
            condition="damaged",
            refund_amount=Decimal("20"),
        )
    )
    db.commit()
    return location, products


def test_fr6_2_ut_1_and_it_1_sales_trend_ranks_and_nets_returns(client, make_user, db):
    manager = make_user("trend_manager", role="manager")
    location, products = _seed_report(db, manager.id)
    assert login(client, "trend_manager").status_code == 200

    response = client.get(
        "/api/reporting/sales-trend",
        params={
            "date_from": (datetime.now(UTC) - timedelta(days=3)).date().isoformat(),
            "date_to": datetime.now(UTC).date().isoformat(),
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    row = next(item for item in body["best"] if item["product_id"] == products[0].id)
    assert (row["units_sold"], row["units_returned"], row["net_units"]) == (5, 2, 3)
    assert Decimal(row["net_amount"]) == Decimal("30")
    assert row["current_stock"] == 7
    assert body["totals"]["products_with_zero_sales"] == 2
    assert body["worst"][-1]["product_id"] == products[0].id
    assert location.id == body["location_id"] or body["location_id"] is None


def test_fr6_2_ut_3_sales_trend_rejects_invalid_ranges(client, make_user):
    make_user("trend_validation_manager", role="manager")
    assert login(client, "trend_validation_manager").status_code == 200
    response = client.get(
        "/api/reporting/sales-trend",
        params={"date_from": "2026-03-01", "date_to": "2026-02-01"},
    )
    assert response.status_code == 422
