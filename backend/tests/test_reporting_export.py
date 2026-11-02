"""CSV and PDF export of reports (FR-6.5)."""

import csv
import io
import re
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from io import BytesIO

import pytest
from pypdf import PdfReader

from app.modules.product._internal.models import Category, Product
from app.modules.purchasing._internal.models import SupplierPriceHistory
from app.modules.reporting._internal.export import ReportTable, csv_chunks, export_filename
from app.modules.stock._internal.models import ItemCost, Location, StockLevel
from tests.helpers import login
from tests.test_supplier_performance import add_order, create_supplier_product

TODAY = datetime.now(UTC).date()
PERIOD = f"date_from={(TODAY - timedelta(days=30)).isoformat()}&date_to={TODAY.isoformat()}"
# Every report and the query its on-screen version needs (FR-6.5: all four report types).
REPORT_QUERY = {
    "valuation": "",
    "reorder": "",
    "sales-trend": PERIOD,
    "supplier-performance": PERIOD,
}
REPORTS = list(REPORT_QUERY)
FIRST_COLUMN = {
    "valuation": "Product / SKU",
    "reorder": "Product / SKU",
    "sales-trend": "Rank",
    "supplier-performance": "Supplier",
}


def _seed(db, *, names=("Export Item",), prefix="EXP", quantity=3, location_name="Export Store"):
    location = Location(name=location_name, type="store")
    category = Category(name=f"{prefix} Category")
    db.add_all([location, category])
    db.flush()
    products = [
        Product(
            sku=f"{prefix}-{index}",
            name=name,
            category_id=category.id,
            brand="Test",
            price=Decimal("100"),
        )
        for index, name in enumerate(names)
    ]
    db.add_all(products)
    db.flush()
    for product in products:
        db.add(StockLevel(product_id=product.id, location_id=location.id, quantity=quantity))
        db.add(ItemCost(product_id=product.id, average_cost=Decimal("10")))
    db.commit()
    return location


def _manager(client, make_user, name="export_manager"):
    make_user(name, role="manager")
    assert login(client, name).status_code == 200


def _csv_rows(response):
    return list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))


@pytest.mark.parametrize("report", REPORTS)
@pytest.mark.parametrize("export_format", ["csv", "pdf"])
def test_fr6_5_every_report_exports_in_both_formats(client, make_user, db, report, export_format):
    _seed(db, prefix=f"ALL-{report}-{export_format}")
    create_supplier_product(db)
    _manager(client, make_user, f"export_all_{report}_{export_format}")

    response = client.get(
        f"/api/reporting/{report}/export?format={export_format}&{REPORT_QUERY[report]}"
    )

    assert response.status_code == 200, response.text
    assert "attachment" in response.headers["content-disposition"]
    if export_format == "pdf":
        assert response.headers["content-type"] == "application/pdf"
        assert response.content.startswith(b"%PDF-")
    else:
        assert response.headers["content-type"].startswith("text/csv")
        assert _csv_rows(response)[0][0] == FIRST_COLUMN[report]


def _pdf_text(content: bytes) -> str:
    return " ".join(page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages)


def test_fr6_1_it_2_valuation_csv_and_pdf_carry_the_same_data_as_the_screen(client, make_user, db):
    location = _seed(db, prefix="PAIR", names=("Pair Item A", "Pair Item B"), quantity=6)
    _manager(client, make_user, "export_pair")
    query = f"location_id={location.id}"

    screen = client.get(f"/api/reporting/valuation?{query}").json()
    rows = _csv_rows(client.get(f"/api/reporting/valuation/export?format=csv&{query}"))
    pdf = _pdf_text(client.get(f"/api/reporting/valuation/export?format=pdf&{query}").content)

    assert len(rows) == 1 + len(screen["items"]) + 1
    for row in rows[1:-1]:
        for cell in (row[0], row[2], row[3], row[5]):
            assert cell in pdf
    assert rows[-1][1] == f"{Decimal(screen['total_value']):.2f}"
    assert rows[-1][1] in pdf


def test_supplier_performance_export_matches_the_on_screen_report(client, make_user, db):
    manager = make_user("export_supplier_manager", role="manager")
    supplier, product, location = create_supplier_product(db)
    received = datetime.combine(TODAY - timedelta(days=3), time(10), tzinfo=UTC)
    for index, (expected_offset, accepted) in enumerate(((0, (5,)), (-1, (3,)))):
        add_order(
            db,
            manager,
            supplier,
            product,
            location,
            suffix=f"exp-{index}",
            created_on=TODAY - timedelta(days=10),
            expected_on=received.date() + timedelta(days=expected_offset),
            ordered=5,
            accepted=accepted,
            receipt_dates=(received,),
            unit_price=Decimal("10.00") + index,
        )
    db.add_all(
        SupplierPriceHistory(
            supplier_id=supplier.id,
            product_id=product.id,
            unit_price=price,
            recorded_at=received + timedelta(hours=hour),
        )
        for hour, price in enumerate((Decimal("10.00"), Decimal("11.00")))
    )
    db.commit()
    assert login(client, manager.username).status_code == 200
    query = f"{PERIOD}&supplier_ids={supplier.id}"

    [screen] = client.get(f"/api/reporting/supplier-performance?{query}").json()["suppliers"]
    csv_response = client.get(f"/api/reporting/supplier-performance/export?format=csv&{query}")
    pdf_response = client.get(f"/api/reporting/supplier-performance/export?format=pdf&{query}")

    assert csv_response.status_code == 200, csv_response.text
    assert re.search(
        r'filename="Supplier_Performance_Report_\d{4}-\d{2}-\d{2}\.csv"',
        csv_response.headers["content-disposition"],
    )
    rows = _csv_rows(csv_response)
    assert rows[1][:8] == [
        screen["supplier_name"],
        str(screen["purchase_order_count"]),
        f"{Decimal(screen['total_order_value']):.2f}",
        f"{screen['on_time_delivery_count']} of {screen['eligible_delivery_count']}",
        f"{Decimal(screen['on_time_delivery_rate']):.2f}%",
        str(screen["quantity_ordered"]),
        str(screen["quantity_accepted"]),
        f"{Decimal(screen['fulfilment_accuracy']):.2f}%",
    ]
    assert rows[1][4] == "50.00%"
    assert rows[1][8] == f"{product.sku}: 10.00 -> 11.00, +1.00 (+10.00%), 2 receipts"
    pdf = _pdf_text(pdf_response.content)
    assert "Supplier Performance Report" in pdf
    assert screen["supplier_name"] in pdf
    assert "50.00%" in pdf
    assert (
        client.get(
            f"/api/reporting/supplier-performance/export?format=csv&{PERIOD}&supplier_ids=999999"
        ).status_code
        == 404
    )


def test_fr6_5_csv_matches_the_on_screen_valuation(client, make_user, db):
    location = _seed(db, prefix="MATCH", names=("Match Item",), quantity=4)
    _manager(client, make_user, "export_match")

    screen = client.get(f"/api/reporting/valuation?location_id={location.id}").json()
    rows = _csv_rows(
        client.get(f"/api/reporting/valuation/export?format=csv&location_id={location.id}")
    )

    assert rows[0][0] == "Product / SKU"
    assert len(rows) == 1 + len(screen["items"]) + 1
    assert rows[1][:4] == ["Match Item (MATCH-0)", "—", "Export Store", "4"]
    assert Decimal(rows[1][5]) == Decimal(screen["items"][0]["value"])
    assert rows[-1] == ["Total inventory value", f"{Decimal(screen['total_value']):.2f}"]


def test_fr6_5_ut_3_commas_and_quotes_stay_in_one_cell(client, make_user, db):
    name = 'Cable, "Premium"'
    location = _seed(db, prefix="ESC", names=(name,))
    _manager(client, make_user, "export_escape")

    response = client.get(f"/api/reporting/valuation/export?format=csv&location_id={location.id}")

    assert '"Cable, ""Premium"" (ESC-0)"' in response.content.decode("utf-8")
    rows = _csv_rows(response)
    assert rows[1][0] == f"{name} (ESC-0)"
    assert len(rows[1]) == len(rows[0])


def test_csv_cells_starting_with_formula_characters_are_neutralised():
    table = ReportTable(title="T", columns=["A"], rows=[["=SUM(A1)"], ["+1"], ["@x"], ["ok"]])

    text = "".join(csv_chunks(table)).lstrip("﻿")

    assert text.splitlines()[1:] == ["'=SUM(A1)", "'+1", "'@x", "ok"]


def test_fr6_5_it_2_pdf_header_has_title_time_and_filter(client, make_user, db):
    location = _seed(db, prefix="HDR", location_name="Header Store")
    _manager(client, make_user, "export_header")

    response = client.get(f"/api/reporting/valuation/export?format=pdf&location_id={location.id}")

    assert response.status_code == 200
    from io import BytesIO

    from pypdf import PdfReader

    text = " ".join(
        page.extract_text() or "" for page in PdfReader(BytesIO(response.content)).pages
    )
    assert "Stock Valuation Report" in text
    assert "Generated: " in text
    assert "Location: Header Store" in text


def test_fr6_5_it_3_five_thousand_rows_export_without_truncation(client, make_user, db):
    names = tuple(f"Bulk Item {index}" for index in range(5200))
    location = _seed(db, prefix="BULK", names=names)
    _manager(client, make_user, "export_bulk")

    csv_response = client.get(
        f"/api/reporting/valuation/export?format=csv&location_id={location.id}"
    )
    pdf_response = client.get(
        f"/api/reporting/valuation/export?format=pdf&location_id={location.id}"
    )

    assert len(_csv_rows(csv_response)) == 1 + 5200 + 1
    assert pdf_response.status_code == 200
    assert pdf_response.content.startswith(b"%PDF-")


@pytest.mark.parametrize("role", ["cashier", "staff"])
@pytest.mark.parametrize("report", REPORTS)
def test_fr6_5_st_1_export_is_denied_where_the_report_is_denied(client, make_user, role, report):
    make_user(f"export_{role}_{report}", role=role, location_id=1)
    assert login(client, f"export_{role}_{report}").status_code == 200

    query = REPORT_QUERY[report]
    assert client.get(f"/api/reporting/{report}?{query}").status_code == 403
    assert client.get(f"/api/reporting/{report}/export?format=csv&{query}").status_code == 403
    assert client.get(f"/api/reporting/{report}/export?format=pdf&{query}").status_code == 403


def test_export_requires_login_and_a_known_format_and_location(client, make_user):
    assert client.get("/api/reporting/valuation/export?format=csv").status_code == 401
    _manager(client, make_user, "export_errors")
    assert client.get("/api/reporting/valuation/export?format=xls").status_code == 422
    assert client.get("/api/reporting/valuation/export").status_code == 422
    assert (
        client.get("/api/reporting/valuation/export?format=csv&location_id=999999").status_code
        == 404
    )


def test_fr6_5_st_2_file_name_has_report_type_and_date(client, make_user, db):
    assert (
        export_filename("Sales Trend Report", datetime(2026, 9, 7, tzinfo=UTC), "pdf")
        == "Sales_Trend_Report_2026-09-07.pdf"
    )
    _seed(db, prefix="NAME")
    _manager(client, make_user, "export_name")

    response = client.get("/api/reporting/valuation/export?format=csv")

    assert re.search(
        r'filename="Stock_Valuation_Report_\d{4}-\d{2}-\d{2}\.csv"',
        response.headers["content-disposition"],
    )
