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


def _sale(db, location, user_id: int, product, quantity: int) -> None:
    sale = Sale(
        location_id=location.id,
        cashier_id=user_id,
        subtotal=Decimal("10") * quantity,
        total=Decimal("10") * quantity,
        sold_at=datetime.now(UTC) - timedelta(days=1),
    )
    db.add(sale)
    db.flush()
    db.add(
        SaleLine(
            sale_id=sale.id,
            product_id=product.id,
            quantity=quantity,
            unit_price=Decimal("10"),
            line_total=Decimal("10") * quantity,
        )
    )


def _period() -> dict[str, str]:
    return {
        "date_from": (datetime.now(UTC) - timedelta(days=3)).date().isoformat(),
        "date_to": datetime.now(UTC).date().isoformat(),
    }


def _two_store_sales(db, user_id: int):
    chennai = Location(name="Trend Chennai", type="store")
    bengaluru = Location(name="Trend Bengaluru", type="store")
    category = Category(name="Trend Split Category")
    db.add_all([chennai, bengaluru, category])
    db.flush()
    phone, cable = (
        Product(
            sku=f"SPLIT-{name}",
            name=f"Split {name}",
            category_id=category.id,
            brand="Trend",
            price=Decimal("10"),
        )
        for name in ("Phone", "Cable")
    )
    db.add_all([phone, cable])
    db.flush()
    _sale(db, chennai, user_id, phone, 4)
    _sale(db, bengaluru, user_id, phone, 6)
    _sale(db, bengaluru, user_id, cable, 3)
    db.commit()
    return chennai, bengaluru, phone, cable


def _units(body, product) -> int:
    rows = body["best"] + body["worst"]
    return next(row["net_units"] for row in rows if row["product_id"] == product.id)


def test_fr6_2_it_2_unfiltered_report_is_the_sum_of_both_locations(client, make_user, db):
    manager = make_user("trend_split_manager", role="manager")
    chennai, bengaluru, phone, cable = _two_store_sales(db, manager.id)
    assert login(client, manager.username).status_code == 200

    combined = client.get("/api/reporting/sales-trend", params=_period()).json()
    only_chennai = client.get(
        "/api/reporting/sales-trend", params={**_period(), "location_id": chennai.id}
    ).json()
    only_bengaluru = client.get(
        "/api/reporting/sales-trend", params={**_period(), "location_id": bengaluru.id}
    ).json()

    assert (_units(only_chennai, phone), _units(only_bengaluru, phone)) == (4, 6)
    assert _units(combined, phone) == 10
    assert _units(combined, cable) == 3
    assert combined["totals"]["net_units"] == (
        only_chennai["totals"]["net_units"] + only_bengaluru["totals"]["net_units"]
    )
    assert combined["location_id"] is None


def test_fr6_2_it_3_csv_and_pdf_exports_match_the_on_screen_ranking(client, make_user, db):
    import csv
    import io

    from tests.test_invoices import _pdf_text

    manager = make_user("trend_export_manager", role="manager")
    _chennai, _bengaluru, phone, cable = _two_store_sales(db, manager.id)
    assert login(client, manager.username).status_code == 200

    screen = client.get("/api/reporting/sales-trend", params={**_period(), "limit": 100}).json()
    csv_response = client.get(
        "/api/reporting/sales-trend/export", params={**_period(), "format": "csv"}
    )
    pdf_response = client.get(
        "/api/reporting/sales-trend/export", params={**_period(), "format": "pdf"}
    )

    assert csv_response.status_code == 200, csv_response.text
    rows = list(csv.reader(io.StringIO(csv_response.content.decode("utf-8-sig"))))
    by_product = {row[1]: row for row in rows[1:] if row and row[0].isdigit()}
    for item in (phone, cable):
        screen_row = next(row for row in screen["best"] if row["product_id"] == item.id)
        csv_row = by_product[f"{item.name} ({item.sku})"]
        assert csv_row[0] == str(screen_row["rank"])
        assert csv_row[6] == str(screen_row["net_units"])
        assert csv_row[9] == f"{Decimal(screen_row['net_amount']):.2f}"
    assert pdf_response.status_code == 200
    pdf = _pdf_text(pdf_response.content)
    assert "Sales Trend Report" in pdf
    assert phone.sku in pdf and cable.sku in pdf
    assert (
        f"Net units: {screen['totals']['net_units']}" in pdf
        or str(screen["totals"]["net_units"]) in pdf
    )
