"""Valuation and reorder reports consume stock's public position service."""

from decimal import Decimal

from app.modules.product._internal.models import Category, Product
from app.modules.purchasing._internal.models import Supplier, SupplierProduct
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


def test_valuation_uses_average_cost_then_active_supplier_catalog_price(client, make_user, db):
    location = Location(name="Valuation Cost Store", type="store")
    category = Category(name="Valuation Cost Category")
    supplier = Supplier(name="Valuation Active Supplier", is_active=True)
    cheaper_supplier = Supplier(name="Valuation Cheaper Supplier", is_active=True)
    inactive_supplier = Supplier(name="Valuation Inactive Supplier", is_active=False)
    db.add_all([location, category, supplier, cheaper_supplier, inactive_supplier])
    db.flush()
    catalog_item, average_cost_item, zero_cost_item, no_cost_item = (
        Product(
            sku=f"VAL-COST-{suffix}",
            name=f"Cost {suffix}",
            category_id=category.id,
            brand="Test",
            price=Decimal("100"),
        )
        for suffix in ("CATALOG", "AVERAGE", "ZERO", "MISSING")
    )
    db.add_all([catalog_item, average_cost_item, zero_cost_item, no_cost_item])
    db.flush()
    db.add_all(
        [
            StockLevel(product_id=catalog_item.id, location_id=location.id, quantity=3),
            StockLevel(product_id=average_cost_item.id, location_id=location.id, quantity=2),
            StockLevel(product_id=zero_cost_item.id, location_id=location.id, quantity=1),
            StockLevel(product_id=no_cost_item.id, location_id=location.id, quantity=4),
            ItemCost(product_id=average_cost_item.id, average_cost=Decimal("10.1234")),
            ItemCost(product_id=zero_cost_item.id, average_cost=Decimal("0")),
            SupplierProduct(
                supplier_id=supplier.id,
                product_id=catalog_item.id,
                supplier_price=Decimal("12.35"),
            ),
            SupplierProduct(
                supplier_id=cheaper_supplier.id,
                product_id=catalog_item.id,
                supplier_price=Decimal("11.00"),
            ),
            SupplierProduct(
                supplier_id=supplier.id,
                product_id=average_cost_item.id,
                supplier_price=Decimal("9.00"),
            ),
            SupplierProduct(
                supplier_id=supplier.id,
                product_id=zero_cost_item.id,
                supplier_price=Decimal("9.00"),
            ),
            SupplierProduct(
                supplier_id=inactive_supplier.id,
                product_id=no_cost_item.id,
                supplier_price=Decimal("5.00"),
            ),
        ]
    )
    db.commit()
    make_user("valuation_cost_manager", role="manager")
    assert login(client, "valuation_cost_manager").status_code == 200

    response = client.get("/api/reporting/valuation")

    assert response.status_code == 200, response.text
    body = response.json()
    rows = {row["sku"]: row for row in body["items"]}
    assert Decimal(rows["VAL-COST-CATALOG"]["unit_cost"]) == Decimal("11.00")
    assert Decimal(rows["VAL-COST-CATALOG"]["value"]) == Decimal("33.00")
    assert rows["VAL-COST-CATALOG"]["cost_not_set"] is False
    assert Decimal(rows["VAL-COST-AVERAGE"]["unit_cost"]) == Decimal("10.1234")
    assert Decimal(rows["VAL-COST-AVERAGE"]["value"]) == Decimal("20.2468")
    assert Decimal(rows["VAL-COST-ZERO"]["unit_cost"]) == Decimal("0")
    assert rows["VAL-COST-ZERO"]["cost_not_set"] is False
    assert Decimal(rows["VAL-COST-MISSING"]["unit_cost"]) == Decimal("0")
    assert Decimal(rows["VAL-COST-MISSING"]["value"]) == Decimal("0")
    assert rows["VAL-COST-MISSING"]["cost_not_set"] is True
    assert Decimal(body["total_value"]) == Decimal("53.2468")

    db.query(ItemCost).filter_by(product_id=average_cost_item.id).one().average_cost = Decimal(
        "12.5000"
    )
    db.commit()
    refreshed = client.get("/api/reporting/valuation")
    assert Decimal(refreshed.json()["total_value"]) == Decimal("58.0000")


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


def test_cashier_cannot_access_stock_valuation(client, make_user):
    make_user("report_cashier", role="cashier", location_id=1)
    assert login(client, "report_cashier").status_code == 200
    assert client.get("/api/reporting/valuation").status_code == 403
