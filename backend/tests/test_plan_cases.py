"""Test plan cases with no earlier test (see TRACEABILITY.md).

Each test is named after its ID in `Documents/Test_Plan_Document.docx`.
"""

from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.config import Settings, get_settings
from app.main import app
from app.modules.product._internal.models import Product
from app.modules.reporting.service import valuation_rows
from app.modules.stock import update_stock
from app.modules.stock._internal.models import ItemCost, Location, StockLevel
from tests.helpers import SETTINGS, login
from tests.test_notifications import create_alert_item
from tests.test_product_search import seed_catalog
from tests.test_products import category, product_payload
from tests.test_purchase_orders import create_fixture_data, create_payload, signed_in
from tests.test_stock_adjustments import adjust
from tests.test_stock_transfers import create_transfer_data

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
SCRIPT = '<script>alert("xss")</script>'


def test_fr1_1_it_3_uploaded_image_is_stored_and_served(client, db, make_user, tmp_path):
    make_user("image_manager", role="manager")
    cat = category(db)
    login(client, "image_manager")
    app.dependency_overrides[get_settings] = lambda: SETTINGS.model_copy(
        update={"product_image_dir": str(tmp_path)}
    )
    product = client.post("/api/product", json=product_payload(cat.id)).json()

    uploaded = client.post(
        f"/api/product/{product['id']}/images", files={"file": ("a54.png", PNG, "image/png")}
    )

    assert uploaded.status_code == 201, uploaded.text
    assert len(list(tmp_path.iterdir())) == 1
    listed = client.get(f"/api/product/{product['id']}/images").json()
    assert [image["id"] for image in listed] == [uploaded.json()["id"]]
    served = client.get(f"/api/product/images/{uploaded.json()['id']}")
    assert served.status_code == 200
    assert served.content == PNG


def test_fr1_1_st_1_add_product_flow_from_login_to_catalog(client, db, make_user):
    make_user("flow_manager", role="manager")
    cat = category(db)
    assert client.get("/api/product").status_code == 401

    assert login(client, "flow_manager").status_code == 200
    created = client.post("/api/product", json=product_payload(cat.id, sku="SKU-FLOW-1"))

    assert created.status_code == 201
    shown = client.get(f"/api/product/{created.json()['id']}").json()
    assert shown["name"] == "Phone"
    assert [item["sku"] for item in client.get("/api/product").json()["items"]] == ["SKU-FLOW-1"]


def test_fr2_3_ut_3_and_fr8_1_ut_2_alert_only_at_or_below_threshold(client, make_user, db):
    product, location, _, _ = create_alert_item(db, quantity=25, threshold=10)
    make_user("alert_threshold_manager", role="manager")
    login(client, "alert_threshold_manager")

    def sell(quantity):
        update_stock(
            db,
            product_id=product.id,
            variant_id=None,
            location_id=location.id,
            quantity_delta=-quantity,
            movement_type="sale",
        )

    sell(5)  # 20, above the threshold
    assert client.get("/api/notifications/alerts").json() == []
    sell(10)  # 10, at the threshold
    [alert] = client.get("/api/notifications/alerts").json()
    assert alert["alert_type"] == "low_stock"
    assert alert["product_name"] == product.name
    assert alert["quantity"] == 10


def test_fr2_4_it_2_adjustment_is_in_the_valuation_report(client, make_user, db):
    source, _, product = create_transfer_data(db, source_quantity=10)
    db.add(ItemCost(product_id=product.id, average_cost=Decimal("10.00")))
    db.commit()
    make_user("adjust_report_manager", role="manager")
    login(client, "adjust_report_manager")
    before = Decimal(
        client.get(f"/api/reporting/valuation?location_id={source.id}").json()["total_value"]
    )

    assert adjust(client, product, source, -3, "Damaged in handling").status_code == 201

    report = client.get(f"/api/reporting/valuation?location_id={source.id}").json()
    assert before == Decimal("100")
    assert Decimal(report["total_value"]) == Decimal("70")
    assert report["items"][0]["quantity"] == 7


def test_fr2_5_ut_3_duplicate_serial_number_is_rejected(conn):
    category_id = conn.execute(
        text("INSERT INTO categories (name) VALUES ('Serials') RETURNING id")
    ).scalar()
    product_id = conn.execute(
        text(
            "INSERT INTO products (name, sku, category_id, brand, price) "
            "VALUES ('Smart TV 43-inch', 'SKU-EL-3001', :c, 'Test', 100) RETURNING id"
        ),
        {"c": category_id},
    ).scalar()
    insert = text(
        "INSERT INTO serial_numbers (serial_number, product_id) VALUES ('SN-TV-000123', :p)"
    )
    conn.execute(insert, {"p": product_id})

    with pytest.raises(IntegrityError, match="serial_number"):
        conn.execute(insert, {"p": product_id})


def test_fr3_1_it_3_supplier_edit_shows_on_existing_purchase_order(client, make_user, db):
    supplier, location, product = create_fixture_data(db)
    signed_in(client, make_user, "manager")
    order = client.post(
        "/api/purchasing/purchase-orders", json=create_payload(supplier, location, product)
    ).json()

    edited = client.patch(
        f"/api/purchasing/suppliers/{supplier.id}", json={"name": "TechDistributors Pvt Ltd"}
    )

    assert edited.status_code == 200, edited.text
    shown = client.get(f"/api/purchasing/purchase-orders/{order['id']}").json()
    assert shown["supplier_name"] == "TechDistributors Pvt Ltd"
    assert shown["lines"][0]["unit_price"] == order["lines"][0]["unit_price"]


def test_fr6_1_ut_3_zero_stock_adds_no_value(db):
    location = Location(name="Zero Value Store", type="store")
    cat = category(db)
    db.add(location)
    db.flush()
    zero, stocked = (
        Product(sku=sku, name=sku, category_id=cat.id, brand="Test", price=Decimal("5"))
        for sku in ("ZERO-VALUE-A", "ZERO-VALUE-B")
    )
    db.add_all([zero, stocked])
    db.flush()
    for product, quantity in ((zero, 0), (stocked, 4)):
        db.add(StockLevel(product_id=product.id, location_id=location.id, quantity=quantity))
        db.add(ItemCost(product_id=product.id, average_cost=Decimal("25")))
    db.commit()

    rows, total = valuation_rows(db, location_id=location.id)

    assert total == Decimal("100")
    assert all(value == 0 for position, value in rows if position.quantity == 0)


def test_sec_inp_2_it_1_search_is_not_injectable(client, db, make_user):
    make_user("injection_manager", role="manager")
    seed_catalog(db)
    login(client, "injection_manager")
    total = client.get("/api/product").json()["total"]

    for term in ("'; DROP TABLE products; --", "' OR '1'='1", "x') UNION SELECT 1 --"):
        response = client.get("/api/product", params={"q": term})
        assert response.status_code == 200
        assert response.json()["total"] == 0

    assert client.get("/api/product").json()["total"] == total
    assert db.scalar(select(Product.id).limit(1)) is not None


@pytest.mark.parametrize(
    "params",
    [
        {"sort": "price; DROP TABLE products"},
        {"sort": "(SELECT 1)"},
        {"category_id": "1 OR 1=1"},
        {"min_price": "0; DELETE FROM products"},
    ],
)
def test_sec_inp_2_it_2_filter_and_sort_parameters_are_not_injectable(
    client, db, make_user, params
):
    make_user("injection_filter_manager", role="manager")
    seed_catalog(db)
    login(client, "injection_filter_manager")

    response = client.get("/api/product", params=params)

    assert response.status_code in (200, 400, 422)
    assert client.get("/api/product").json()["total"] == 3


def test_sec_inp_3_it_1_script_in_product_name_is_returned_as_data(client, db, make_user):
    make_user("script_manager", role="manager")
    cat = category(db)
    login(client, "script_manager")

    created = client.post("/api/product", json=product_payload(cat.id, name=SCRIPT))

    assert created.status_code == 201
    listed = client.get("/api/product")
    assert listed.headers["content-type"].startswith("application/json")
    assert listed.json()["items"][0]["name"] == SCRIPT


def test_sec_dat_6_st_1_no_credentials_in_source():
    root = Path(__file__).resolve().parent.parent
    patterns = (
        "-----BEGIN RSA PRIVATE KEY",
        "-----BEGIN OPENSSH PRIVATE KEY",
        "-----BEGIN PRIVATE KEY",
    )
    patterns += ("AKIA", "ghp_", "sk-ant-")
    offenders = [
        str(path.relative_to(root))
        for folder in ("app", "migrations", "scripts", "tests")
        for path in (root / folder).rglob("*.py")
        if path != Path(__file__)
        and any(pattern in path.read_text(encoding="utf-8") for pattern in patterns)
    ]
    assert offenders == []
    assert not (root / ".env").exists() or ".env" in (root.parent / ".gitignore").read_text()


def test_sec_dat_6_st_2_secrets_come_from_the_environment(monkeypatch):
    for name in ("DATABASE_URL", "SEED_USER_PASSWORD", "SMTP_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    defaults = Settings()
    assert (defaults.database_url, defaults.seed_user_password, defaults.smtp_password) == (
        "",
        "",
        "",
    )

    monkeypatch.setenv("DATABASE_URL", "postgresql://u:from-env@db/x")
    monkeypatch.setenv("SEED_USER_PASSWORD", "seed-from-env")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-from-env")
    configured = Settings()
    assert configured.database_url == "postgresql://u:from-env@db/x"
    assert configured.seed_user_password == "seed-from-env"
    assert configured.smtp_password == "smtp-from-env"
