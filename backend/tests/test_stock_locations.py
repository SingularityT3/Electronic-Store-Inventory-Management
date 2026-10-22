"""Location management API (Issue #14)."""

from sqlalchemy.orm import Session

from app.modules.stock._internal.models import Location
from tests.helpers import login


def signed_in_client(client, make_user, role: str, username: str, location_id: int | None = None):
    make_user(username, role=role, location_id=location_id)
    assert login(client, username).status_code == 200
    return client


def create_test_location(db: Session) -> int:
    location = Location(name="Test Store", type="store")
    db.add(location)
    db.commit()
    return location.id


def test_admin_and_manager_can_create_and_edit_locations(client, make_user):
    for role in ("admin", "manager"):
        username = f"{role}_locations"
        authorized = signed_in_client(client, make_user, role, username)
        created = authorized.post(
            "/api/stock/locations",
            json={
                "name": f"{role.title()} Store",
                "type": "store",
                "address": "12 Main Street",
            },
        )
        assert created.status_code == 201, created.text
        location = created.json()
        assert location["name"] == f"{role.title()} Store"
        assert location["type"] == "store"
        assert location["address"] == "12 Main Street"
        assert location["is_active"] is True

        edited = authorized.patch(
            f"/api/stock/locations/{location['id']}",
            json={"type": "warehouse", "address": "New address", "is_active": False},
        )
        assert edited.status_code == 200, edited.text
        assert edited.json() == {
            **location,
            "type": "warehouse",
            "address": "New address",
            "is_active": False,
        }
        authorized.post("/api/auth/logout")


def test_staff_and_cashier_cannot_manage_locations(client, make_user, db):
    location_id = create_test_location(db)
    for role in ("staff", "cashier"):
        username = f"{role}_locations"
        unauthorized = signed_in_client(client, make_user, role, username, location_id)
        create = unauthorized.post(
            "/api/stock/locations", json={"name": "Blocked", "type": "store"}
        )
        edit = unauthorized.patch("/api/stock/locations/1", json={"name": "Blocked"})
        assert create.status_code == 403
        assert edit.status_code == 403
        unauthorized.post("/api/auth/logout")


def test_location_listing_keeps_stock_view_permission(client, make_user):
    admin = signed_in_client(client, make_user, "admin", "admin_locations_list")
    created = admin.post("/api/stock/locations", json={"name": "Visible Store", "type": "store"})
    assert created.status_code == 201, created.text
    location_id = created.json()["id"]
    other = admin.post("/api/stock/locations", json={"name": "Other Store", "type": "store"})
    assert other.status_code == 201, other.text
    all_locations = admin.get("/api/stock/locations")
    assert [location["name"] for location in all_locations.json()] == [
        "Other Store",
        "Visible Store",
    ]
    admin.post("/api/auth/logout")

    staff = signed_in_client(client, make_user, "staff", "staff_locations_view", location_id)
    listed = staff.get("/api/stock/locations")
    assert listed.status_code == 200
    locations = listed.json()
    assert len(locations) == 1
    assert locations[0]["name"] == "Visible Store"
    assert locations[0]["type"] == "store"
    assert set(locations[0]) == {"id", "name", "type"}
    staff.post("/api/auth/logout")

    cashier = signed_in_client(client, make_user, "cashier", "cashier_locations_view", location_id)
    assert cashier.get("/api/stock/locations").status_code == 403


def test_location_creation_rejects_invalid_type(client, make_user):
    admin = signed_in_client(client, make_user, "admin", "admin_invalid_location")
    response = admin.post("/api/stock/locations", json={"name": "Invalid", "type": "office"})
    assert response.status_code == 422
    existing = admin.post(
        "/api/stock/locations", json={"name": "Valid Store", "type": "store"}
    ).json()
    invalid_edit = admin.patch(f"/api/stock/locations/{existing['id']}", json={"type": "office"})
    assert invalid_edit.status_code == 422


def test_duplicate_location_name_returns_conflict(client, make_user):
    admin = signed_in_client(client, make_user, "admin", "admin_duplicate_location")
    payload = {"name": "Duplicate Store", "type": "store"}
    assert admin.post("/api/stock/locations", json=payload).status_code == 201
    duplicate = admin.post("/api/stock/locations", json=payload)
    assert duplicate.status_code == 409


def test_edit_location_rejects_duplicate_name_and_nonexistent_id(client, make_user):
    admin = signed_in_client(client, make_user, "admin", "admin_edit_location")
    first = admin.post("/api/stock/locations", json={"name": "First Store", "type": "store"}).json()
    admin.post("/api/stock/locations", json={"name": "Second Store", "type": "store"})

    duplicate = admin.patch(f"/api/stock/locations/{first['id']}", json={"name": "Second Store"})
    assert duplicate.status_code == 409
    unchanged = admin.patch(f"/api/stock/locations/{first['id']}", json={"address": "Still valid"})
    assert unchanged.status_code == 200
    assert unchanged.json()["name"] == "First Store"
    missing = admin.patch("/api/stock/locations/999999", json={"name": "Missing"})
    assert missing.status_code == 404
