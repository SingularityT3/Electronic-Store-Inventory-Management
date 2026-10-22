"""Valuation and reorder reports consume stock's public position service."""

from decimal import Decimal

from app.modules.product._internal.models import Category, Product
from app.modules.stock._internal.models import ItemCost, Location, StockLevel
from tests.helpers import login


def test_valuation_is_live_and_can_filter_location(client, make_user, db):
    chennai = Location(name="Report Chennai", type="store")
    bengaluru = Location(name="Report Bengaluru", type="warehouse")
    category = Category(name="Report Phones")
    db.add_all([chennai, bengaluru, category])
    db.flush()
    products = [
        Product(
            sku=f"VALUE-{sku}",
            name=name,
            category_id=category.id,
            brand="Test",
            price=Decimal("100"),
        )
        for sku, name in (("A", "Value A"), ("B", "Value B"), ("C", "Value C"))
    ]
    db.add_all(products)
    db.flush()
    quantities = [
        (products[0], chennai, 50, Decimal("500")),
        (products[1], chennai, 20, Decimal("1000")),
        (products[2], bengaluru, 10, Decimal("2000")),
    ]
    for product, location, quantity, cost in quantities:
        db.add(StockLevel(product_id=product.id, location_id=location.id, quantity=quantity))
        db.add(ItemCost(product_id=product.id, average_cost=cost))
    db.commit()
    make_user("report_manager", role="manager")
    assert login(client, "report_manager").status_code == 200

    all_locations = client.get("/api/reporting/valuation")
    assert all_locations.status_code == 200, all_locations.text
    assert Decimal(all_locations.json()["total_value"]) == Decimal("65000")
    chennai_report = client.get(f"/api/reporting/valuation?location_id={chennai.id}")
    assert chennai_report.status_code == 200
    assert Decimal(chennai_report.json()["total_value"]) == Decimal("45000")
    assert {row["location_name"] for row in chennai_report.json()["items"]} == {"Report Chennai"}

    db.add(StockLevel(product_id=products[0].id, location_id=bengaluru.id, quantity=2))
    db.commit()
    updated = client.get("/api/reporting/valuation")
    assert Decimal(updated.json()["total_value"]) == Decimal("66000")


def test_reorder_report_filters_thresholds_and_uses_reorder_to(client, make_user, db):
    location = Location(name="Reorder Store", type="store")
    other_location = Location(name="Other Reorder Store", type="store")
    category = Category(name="Reorder Category")
    db.add_all([location, other_location, category])
    db.flush()
    flagged = Product(
        sku="REORDER-LOW",
        name="Low Stock Product",
        category_id=category.id,
        brand="Test",
        price=Decimal("50"),
    )
    healthy = Product(
        sku="REORDER-OK",
        name="Healthy Product",
        category_id=category.id,
        brand="Test",
        price=Decimal("70"),
    )
    db.add_all([flagged, healthy])
    db.flush()
    db.add_all(
        [
            StockLevel(
                product_id=flagged.id,
                location_id=location.id,
                quantity=3,
                reorder_threshold=5,
                reorder_to_level=12,
            ),
            StockLevel(
                product_id=healthy.id,
                location_id=location.id,
                quantity=6,
                reorder_threshold=5,
                reorder_to_level=10,
            ),
            StockLevel(
                product_id=flagged.id,
                location_id=other_location.id,
                quantity=0,
                reorder_threshold=4,
            ),
        ]
    )
    db.commit()
    make_user("reorder_manager", role="manager")
    assert login(client, "reorder_manager").status_code == 200

    all_locations = client.get("/api/reporting/reorder")
    assert all_locations.status_code == 200, all_locations.text
    assert {(row["location_name"], row["sku"]) for row in all_locations.json()} == {
        ("Reorder Store", "REORDER-LOW"),
        ("Other Reorder Store", "REORDER-LOW"),
    }
    custom = next(row for row in all_locations.json() if row["location_id"] == location.id)
    assert custom["suggested_quantity"] == 9
    defaulted = next(row for row in all_locations.json() if row["location_id"] == other_location.id)
    assert defaulted["reorder_to_level"] == 8
    assert defaulted["suggested_quantity"] == 8

    filtered = client.get(f"/api/reporting/reorder?location_id={location.id}")
    assert filtered.status_code == 200
    assert [row["sku"] for row in filtered.json()] == ["REORDER-LOW"]


def test_staff_cannot_access_stock_reports(client, make_user):
    make_user("report_staff", role="staff", location_id=1)
    assert login(client, "report_staff").status_code == 200
    assert client.get("/api/reporting/valuation").status_code == 403
    assert client.get("/api/reporting/reorder").status_code == 403
