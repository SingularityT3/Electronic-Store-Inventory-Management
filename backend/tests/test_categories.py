"""Category hierarchy API tests (FR1.2-UT-1..3, FR1.2-IT-1..3, FR1.2-ST-2)."""

from sqlalchemy import text

from app.modules.product._internal.models import Product
from tests.helpers import login


def manager(client, make_user):
    make_user("category_manager", role="manager")
    assert login(client, "category_manager").status_code == 200
    return client


def create(client, name, parent_id=None):
    response = client.post("/api/product/categories", json={"name": name, "parent_id": parent_id})
    assert response.status_code == 201, response.text
    return response.json()


def test_admin_creates_tree_in_tree_order_and_invalid_parent_is_not_saved(client, make_user):
    client = manager(client, make_user)
    electronics = create(client, "Electronics")
    mobile = create(client, "Mobile Phones", electronics["id"])
    smartphones = create(client, "Smartphones", mobile["id"])

    assert client.get("/api/product/categories").json() == [
        {
            **electronics,
            "depth": 0,
            "path": [{"id": electronics["id"], "name": "Electronics"}],
            "path_label": "Electronics",
            "product_count": 0,
            "total_product_count": 0,
        },
        {
            **mobile,
            "depth": 1,
            "path": [
                {"id": electronics["id"], "name": "Electronics"},
                {"id": mobile["id"], "name": "Mobile Phones"},
            ],
            "path_label": "Electronics > Mobile Phones",
            "product_count": 0,
            "total_product_count": 0,
        },
        {
            **smartphones,
            "depth": 2,
            "path": [
                {"id": electronics["id"], "name": "Electronics"},
                {"id": mobile["id"], "name": "Mobile Phones"},
                {"id": smartphones["id"], "name": "Smartphones"},
            ],
            "path_label": "Electronics > Mobile Phones > Smartphones",
            "product_count": 0,
            "total_product_count": 0,
        },
    ]
    response = client.post("/api/product/categories", json={"name": "Invalid", "parent_id": 999})
    assert response.status_code == 422
    assert response.json() == {
        "detail": {"field": "parent_id", "message": "Invalid parent category"}
    }
    assert all(item["name"] != "Invalid" for item in client.get("/api/product/categories").json())


def test_cycles_duplicates_delete_and_rollup_counts(client, make_user, db):
    client = manager(client, make_user)
    root = create(client, "Electronics")
    child = create(client, "Mobile Phones", root["id"])
    leaf = create(client, "Smartphones", child["id"])
    product = Product(
        sku="CAT-001",
        name="Phone",
        category_id=leaf["id"],
        brand="Brand",
        price=100,
        is_active=True,
    )
    inactive = Product(
        sku="CAT-002",
        name="Old Phone",
        category_id=leaf["id"],
        brand="Brand",
        price=100,
        is_active=False,
    )
    db.add_all([product, inactive])
    db.commit()

    cycle = client.patch(f"/api/product/categories/{root['id']}", json={"parent_id": leaf["id"]})
    assert cycle.status_code == 422
    duplicate = client.post(
        "/api/product/categories", json={"name": "Mobile Phones", "parent_id": root["id"]}
    )
    assert duplicate.status_code == 422
    categories = {item["id"]: item for item in client.get("/api/product/categories").json()}
    assert categories[root["id"]]["total_product_count"] == 1
    assert categories[root["id"]]["product_count"] == 0
    assert [
        item["name"]
        for item in client.get(f"/api/product/categories/{root['id']}/products").json()["items"]
    ] == ["Phone"]
    blocked = client.delete(f"/api/product/categories/{child['id']}")
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "Cannot delete category with existing subcategories/products"
    assert client.delete(f"/api/product/categories/{leaf['id']}").status_code == 409
    db.execute(text("DELETE FROM products WHERE sku = 'CAT-001'"))
    db.commit()
    assert client.delete(f"/api/product/categories/{leaf['id']}").status_code == 409


def test_staff_and_cashier_can_read_but_cannot_manage(client, make_user):
    for role in ("staff", "cashier"):
        make_user(f"category_{role}", role=role, location_id=1)
        assert login(client, f"category_{role}").status_code == 200
        assert client.get("/api/product/categories").status_code == 200
        assert client.post("/api/product/categories", json={"name": role}).status_code == 403
