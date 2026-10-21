"""Audit log: recording, the Admin-only viewer and immutability (#8).

Test plan cases FR5.3-UT-1..3, FR5.3-IT-1, FR5.3-IT-2 and FR5.3-ST-2 (FR5.3-IT-3 is in
test_rbac.py). Product, stock, purchasing and sales routes arrive with later issues, so their
entries are written here through `audit_service`, the way those modules will write them.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

import pytest
from fastapi.routing import APIRoute
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.main import app
from app.modules.audit import audit_service, changes
from app.modules.audit._internal.models import AuditLog
from tests.helpers import login

ENTRY_FIELDS = {
    "id",
    "occurred_at",
    "user_id",
    "username",
    "module",
    "action",
    "entity_type",
    "entity_id",
    "details",
    "before",
    "after",
}


@pytest.fixture
def admin(client, make_user):
    make_user("admin_asha", role="admin")
    assert login(client, "admin_asha").status_code == 200
    return client


def entries(client, **params) -> list[dict]:
    response = client.get("/api/audit/entries", params=params)
    assert response.status_code == 200, response.text
    return response.json()["entries"]


def record(db, **fields) -> None:
    fields.setdefault("module", "stock")
    fields.setdefault("action", "stock_adjusted")
    audit_service.record(db, **fields)
    db.commit()


# FR5.3-UT-1
def test_login_is_logged_with_user_and_time(admin):
    [entry] = entries(admin)
    assert entry["action"] == "login"
    assert entry["module"] == "auth"
    assert entry["username"] == "admin_asha"
    assert entry["user_id"] is not None
    occurred = datetime.fromisoformat(entry["occurred_at"])
    assert abs(datetime.now(UTC) - occurred) < timedelta(minutes=1)


# FR5.3-UT-2
def test_price_edit_is_logged_with_old_and_new_value(admin, db):
    old = {"name": "Galaxy S24", "price": Decimal("28999.00")}
    new = {"name": "Galaxy S24", "price": Decimal("26999.00")}
    before, after = changes(old, new)
    record(
        db,
        module="product",
        action="product_price_updated",
        user_id=7,
        username="manager_priya",
        entity_type="product",
        entity_id="1",
        before=before,
        after=after,
    )
    [entry] = entries(admin, action="product_price_updated")
    assert entry["username"] == "manager_priya"
    assert entry["before"] == {"price": "28999.00"}
    assert entry["after"] == {"price": "26999.00"}


def test_changes_keeps_only_changed_fields_as_json():
    class Status(StrEnum):
        DRAFT = "draft"
        SENT = "sent"

    before, after = changes(
        {"qty": 1, "status": Status.DRAFT, "due": date(2026, 1, 1), "note": "x"},
        {"qty": 1, "status": Status.SENT, "due": date(2026, 2, 1), "extra": True},
    )
    assert before == {"status": "draft", "due": "2026-01-01", "note": "x", "extra": None}
    assert after == {"status": "sent", "due": "2026-02-01", "note": None, "extra": True}


def test_record_stores_decimals_and_dates_as_json(conn, db):
    record(db, after={"cost": Decimal("10.50"), "on": date(2026, 3, 4), "ids": (1, 2)})
    stored = conn.execute(text("SELECT after FROM audit_log")).scalar_one()
    assert stored == {"cost": "10.50", "on": "2026-03-04", "ids": [1, 2]}


# FR5.3-UT-3
def test_filter_by_user_any_case(admin, db):
    record(db, username="manager_priya")
    record(db, username="staff_arun")
    record(db, username="Manager_Priya", module="purchasing", action="po_created")
    found = entries(admin, username="MANAGER_PRIYA")
    assert [e["action"] for e in found] == ["po_created", "stock_adjusted"]
    assert {e["username"].lower() for e in found} == {"manager_priya"}


def test_filter_by_action_and_module(admin, db):
    record(db, module="stock", action="stock_adjusted")
    record(db, module="stock", action="stock_transferred")
    record(db, module="sales", action="sale_recorded")
    assert [e["action"] for e in entries(admin, action="stock_transferred")] == [
        "stock_transferred"
    ]
    assert {e["action"] for e in entries(admin, module="stock")} == {
        "stock_adjusted",
        "stock_transferred",
    }


def test_filter_by_date_range(admin, conn):
    # occurred_at is the transaction time, so set it directly; inserts are allowed.
    for day in (1, 2, 3):
        conn.execute(
            text(
                "INSERT INTO audit_log (occurred_at, module, action) "
                "VALUES (:at, 'stock', :action)"
            ),
            {"at": datetime(2026, 5, day, 12, tzinfo=UTC), "action": f"day_{day}"},
        )
    found = entries(admin, since="2026-05-02T00:00:00Z", until="2026-05-03T00:00:00Z")
    assert [e["action"] for e in found] == ["day_2"]
    # since is inclusive, until exclusive.
    found = entries(admin, since="2026-05-02T12:00:00Z", until="2026-05-03T12:00:00Z")
    assert [e["action"] for e in found] == ["day_2"]


def test_no_match_is_an_empty_page(admin):
    response = admin.get("/api/audit/entries", params={"username": "nobody"})
    assert response.json() == {"entries": [], "total": 0, "limit": 50, "offset": 0}


def test_bad_date_range_is_rejected(admin):
    since, until = "2026-05-03T00:00:00Z", "2026-05-02T00:00:00Z"
    response = admin.get("/api/audit/entries", params={"since": since, "until": until})
    assert response.status_code == 422
    # A date without an offset is ambiguous.
    response = admin.get("/api/audit/entries", params={"since": "2026-05-02T00:00:00"})
    assert response.status_code == 422


def test_newest_first_with_paging(admin, db):
    for i in range(5):
        record(db, action=f"action_{i}")
    response = admin.get("/api/audit/entries", params={"limit": 2, "offset": 1})
    page = response.json()
    assert page["total"] == 6  # and the login
    assert [e["action"] for e in page["entries"]] == ["action_3", "action_2"]


def test_filter_options_list_what_is_in_the_log(admin, db):
    record(db, username="staff_arun", module="stock", action="stock_adjusted")
    record(db, module="sales", action="sale_recorded")
    assert admin.get("/api/audit/filters").json() == {
        "usernames": ["admin_asha", "staff_arun"],
        "actions": ["login", "sale_recorded", "stock_adjusted"],
        "modules": ["auth", "sales", "stock"],
    }


# FR5.3-IT-1
def test_entries_from_every_module_share_one_structure(admin, db):
    for module, action in [
        ("stock", "stock_adjusted"),
        ("purchasing", "po_created"),
        ("sales", "sale_recorded"),
        ("auth", "user_updated"),
    ]:
        record(db, module=module, action=action, user_id=7, username="manager_priya")
    found = entries(admin, username="manager_priya")
    assert len(found) == 4
    for entry in found:
        assert set(entry) == ENTRY_FIELDS
        assert entry["occurred_at"] and entry["username"] and entry["module"] and entry["action"]


# FR5.3-IT-2
def test_api_has_no_way_to_change_entries():
    audit_routes = [
        r for r in app.routes if isinstance(r, APIRoute) and r.path.startswith("/api/audit")
    ]
    assert audit_routes
    assert all(r.methods == {"GET"} for r in audit_routes)


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
def test_admin_cannot_edit_or_delete_an_entry(admin, conn, method):
    [entry] = entries(admin)
    for path in ("/api/audit/entries", f"/api/audit/entries/{entry['id']}"):
        response = admin.request(method, path, json={"action": "tampered"})
        assert response.status_code in (404, 405)
    assert conn.execute(text("SELECT action FROM audit_log")).scalars().all() == ["login"]


def test_database_rejects_changes_made_through_the_orm(admin, db):
    entry = db.query(AuditLog).one()
    entry.action = "tampered"
    with pytest.raises(DBAPIError, match="append-only"):
        db.commit()
    db.rollback()
    db.delete(db.query(AuditLog).one())
    with pytest.raises(DBAPIError, match="append-only"):
        db.commit()


# FR5.3-ST-2
@pytest.mark.parametrize("role", ["manager", "staff", "cashier"])
@pytest.mark.parametrize("path", ["/api/audit/entries", "/api/audit/filters"])
def test_only_admin_can_view_the_log(client, make_user, conn, role, path):
    make_user(f"{role}_user", role=role, location_id=1)
    assert login(client, f"{role}_user").status_code == 200
    assert client.get(path).status_code == 403
    denied = conn.execute(
        text("SELECT username, details FROM audit_log WHERE action = 'unauthorized_access_attempt'")
    ).one()
    assert denied.username == f"{role}_user"
    assert "audit.view" in denied.details


def test_signed_out_user_cannot_view_the_log(client):
    assert client.get("/api/audit/entries").status_code == 401
