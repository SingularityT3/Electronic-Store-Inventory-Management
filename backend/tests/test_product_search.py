from app.modules.product._internal.models import Category, Product, ProductVariant
from app.modules.stock._internal.models import Location, StockLevel
from tests.helpers import login


def seed_catalog(db):
    root = Category(name="Electronics")
    mobile = Category(name="Mobile Phones", parent_id=None)
    db.add_all([root, mobile])
    db.flush()
    mobile.parent_id = root.id
    smartphones = Category(name="Smartphones", parent_id=mobile.id)
    db.add(smartphones)
    db.flush()
    products = [
        Product(
            name="Samsung Galaxy A54",
            sku="SKU-EL-1001",
            category_id=smartphones.id,
            brand="Samsung",
            price=28999,
        ),
        Product(
            name="Samsung Galaxy M14",
            sku="SKU-EL-1002",
            category_id=smartphones.id,
            brand="Samsung",
            price=13999,
        ),
        Product(
            name="Office Laptop",
            sku="LAP-1001",
            category_id=root.id,
            brand="Other",
            price=50000,
        ),
    ]
    db.add_all(products)
    db.flush()
    db.add(
        ProductVariant(
            product_id=products[0].id,
            sku="VAR-A54-BLACK",
            attributes={"color": "black"},
        )
    )
    db.commit()
    return root, mobile, smartphones, products


def test_search_matches_name_sku_brand_variant_and_category(client, db, make_user):
    make_user("search_manager", role="manager")
    root, mobile, smartphones, products = seed_catalog(db)
    assert login(client, "search_manager").status_code == 200

    assert client.get("/api/product", params={"q": "Galaxy"}).json()["total"] == 2
    assert client.get("/api/product", params={"q": "sku-el-1001"}).json()["items"][0]["sku"] == (
        "SKU-EL-1001"
    )
    assert client.get("/api/product", params={"q": "var-a54-black"}).json()["items"][0]["id"] == (
        products[0].id
    )
    category_result = client.get("/api/product", params={"q": "mobile phones"}).json()
    assert {item["id"] for item in category_result["items"]} == {products[0].id, products[1].id}
    assert client.get("/api/product", params={"q": "Samsung"}).json()["total"] == 2
    assert client.get("/api/product", params={"q": "NonexistentProductXYZ"}).json() == {
        "items": [],
        "total": 0,
        "page": 1,
        "page_size": 50,
    }


def test_search_is_literal_live_and_location_scoped(client, db, make_user):
    manager = make_user("search_manager", role="manager")
    staff = make_user("search_staff", role="staff", location_id=1)
    location = db.get(Location, 1) or Location(name="Search Store", type="store")
    second_location = Location(name="Search Warehouse", type="warehouse")
    db.add_all([location, second_location])
    db.flush()
    staff.location_id = location.id
    product = Product(
        name="O'Brien Phone",
        sku="PERCENT-100%",
        category_id=seed_catalog(db)[0].id,
        brand="Unicode",
        price=100,
    )
    db.add(product)
    db.flush()
    db.add_all(
        [
            StockLevel(product_id=product.id, location_id=location.id, quantity=3),
            StockLevel(product_id=product.id, location_id=second_location.id, quantity=2),
        ]
    )
    db.commit()

    login(client, manager.username)
    response = client.get("/api/product", params={"q": "%"})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["total"] == 0
    assert client.get("/api/product", params={"q": "100%"}).json()["total"] == 0

    login(client, staff.username)
    scoped = client.get("/api/product", params={"q": "O'Brien"}).json()
    assert scoped["items"][0]["stock"] == 3


def test_search_requires_all_roles_and_rejects_long_terms(client, db, make_user):
    category = Category(name="Phones")
    db.add(category)
    db.commit()
    db.add(Product(name="Phone", sku="PHONE-1", category_id=category.id, brand="Brand", price=1))
    db.commit()
    for role, fields in [
        ("admin", {}),
        ("manager", {}),
        ("staff", {"location_id": 1}),
        ("cashier", {"location_id": 1}),
    ]:
        user = make_user(f"search_{role}", role=role, **fields)
        login(client, user.username)
        assert client.get("/api/product", params={"q": "Phone"}).status_code == 200
    assert client.get("/api/product", params={"q": "x" * 101}).status_code == 422
