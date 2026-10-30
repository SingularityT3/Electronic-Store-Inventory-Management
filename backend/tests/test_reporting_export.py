"""CSV and PDF export of reports (FR-6.5)."""

import csv
import io
import re
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.modules.product._internal.models import Category, Product
from app.modules.reporting._internal.export import ReportTable, csv_chunks, export_filename
from app.modules.stock._internal.models import ItemCost, Location, StockLevel
from tests.helpers import login

REPORTS = ["valuation", "reorder"]


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
    _manager(client, make_user, f"export_all_{report}_{export_format}")

    response = client.get(f"/api/reporting/{report}/export?format={export_format}")

    assert response.status_code == 200, response.text
    assert "attachment" in response.headers["content-disposition"]
    if export_format == "pdf":
        assert response.headers["content-type"] == "application/pdf"
        assert response.content.startswith(b"%PDF-")
    else:
        assert response.headers["content-type"].startswith("text/csv")
        assert _csv_rows(response)[0][0] == "Product / SKU"


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
    # Page content is Flate-compressed, so decode it before looking for the text.
    import re as _re
    import zlib

    streams = _re.findall(rb"stream\r?\n(.*?)\r?\nendstream", response.content, _re.S)
    text = b"".join(zlib.decompress(s) for s in streams if s[:1] == b"x").decode("latin-1")
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

    assert client.get(f"/api/reporting/{report}").status_code == 403
    assert client.get(f"/api/reporting/{report}/export?format=csv").status_code == 403
    assert client.get(f"/api/reporting/{report}/export?format=pdf").status_code == 403


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
