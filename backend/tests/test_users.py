"""Admin user account management (FR-5.1, UC-02)."""

from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.helpers import PASSWORD, login


def admin_client(client, make_user):
    make_user("admin_asha", email="admin@example.com", role="admin")
    assert login(client, "admin_asha").status_code == 200
    return client


def user_payload(**overrides):
    payload = {
        "full_name": "Manager Priya",
        "username": "manager_priya",
        "email": "priya@example.com",
        "role": "manager",
        "location_id": None,
    }
    payload.update(overrides)
    return payload


def test_admin_creates_manager_and_invite_is_not_exposed(client, make_user, conn):
    admin = admin_client(client, make_user)
    response = admin.post("/api/auth/users", json=user_payload())
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["role"] == "manager"
    assert "password" not in response.text
    assert "token" not in response.text.lower()
    assert (
        conn.execute(text("SELECT role FROM users WHERE username = 'manager_priya'")).scalar_one()
        == "manager"
    )
    assert (
        conn.execute(text("SELECT action FROM audit_log ORDER BY id")).scalars().all()[-1]
        == "user_created"
    )


def test_invite_link_sets_password_once(client, make_user, monkeypatch):
    link: list[str] = []

    def capture_email(_settings, _to, invite_link, **_kwargs):
        link.append(invite_link)

    monkeypatch.setattr("app.modules.auth.router.send_reset_email", capture_email)
    admin = admin_client(client, make_user)
    response = admin.post("/api/auth/users", json=user_payload())
    assert response.status_code == 201
    token = link[0].split("token=", 1)[1]
    reset = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": token, "new_password": PASSWORD},
    )
    assert reset.status_code == 204
    assert login(client, "manager_priya").status_code == 200
    assert (
        client.post(
            "/api/auth/password-reset/confirm",
            json={"token": token, "new_password": "another-password"},
        ).status_code
        == 400
    )


def test_duplicate_email_and_username_are_rejected_without_saving(client, make_user, conn):
    admin = admin_client(client, make_user)
    admin.post("/api/auth/users", json=user_payload())
    count_after_create = conn.execute(text("SELECT count(*) FROM users")).scalar_one()
    duplicate_email = admin.post(
        "/api/auth/users", json=user_payload(username="other", email="PRIYA@example.com")
    )
    assert duplicate_email.status_code == 409
    assert "email" in duplicate_email.json()["detail"]
    duplicate_username = admin.post(
        "/api/auth/users", json=user_payload(username="MANAGER_PRIYA", email="other@example.com")
    )
    assert duplicate_username.status_code == 409
    assert "username" in duplicate_username.json()["detail"]
    assert conn.execute(text("SELECT count(*) FROM users")).scalar_one() == count_after_create


def test_required_fields_and_location_are_field_errors(client, make_user):
    admin = admin_client(client, make_user)
    missing = admin.post("/api/auth/users", json={})
    assert missing.status_code == 422
    assert set(missing.json()["detail"]) >= {"full_name", "username", "email", "role"}
    for role in ("staff", "cashier"):
        response = admin.post("/api/auth/users", json=user_payload(role=role))
        assert response.status_code == 422
        assert "location_id" in response.json()["detail"]


def test_role_change_applies_on_the_next_request(client, make_user, db):
    db.execute(
        text(
            "INSERT INTO locations (name, type, address) "
            "VALUES ('Main Store', 'store', 'Address')"
        )
    )
    location_id = db.execute(
        text("SELECT id FROM locations WHERE name = 'Main Store'")
    ).scalar_one()
    db.commit()
    target = make_user(
        "staff_user", role="staff", location_id=location_id, email="staff@example.com"
    )
    admin = admin_client(client, make_user)
    target_client = TestClient(client.app)
    assert login(target_client, "staff_user").status_code == 200
    assert target_client.get("/api/stock/locations").status_code == 200
    target.role = "cashier"
    db.commit()
    assert target_client.get("/api/stock/locations").status_code == 403
    target.role = "manager"
    db.commit()
    assert target_client.get("/api/stock/locations").status_code == 200
    assert admin.patch(f"/api/auth/users/{target.id}", json={"role": "manager"}).status_code == 200


def test_non_admin_cannot_call_management_endpoints(client, make_user):
    for role in ("manager", "staff", "cashier"):
        make_user(f"{role}_user", role=role, location_id=1 if role != "manager" else None)
        assert login(client, f"{role}_user").status_code == 200
        assert client.get("/api/auth/users").status_code == 403
        assert client.get("/api/auth/users/1").status_code == 403
        assert client.post("/api/auth/users", json=user_payload()).status_code == 403
        client.post("/api/auth/logout")


def test_deactivation_revokes_session_and_blocks_login(client, make_user, db):
    target = make_user("manager_user", role="manager", email="manager@example.com")
    target_client = TestClient(client.app)
    assert login(target_client, "manager_user").status_code == 200
    admin = admin_client(client, make_user)
    response = admin.post(f"/api/auth/users/{target.id}/deactivate")
    assert response.status_code == 200
    assert target_client.get("/api/auth/me").status_code == 401
    assert login(target_client, "manager_user").status_code == 403
    assert "user_deactivated" in conn_actions(db)


def conn_actions(db):
    return [row[0] for row in db.execute(text("SELECT action FROM audit_log")).all()]


def test_last_admin_and_self_protection(client, make_user):
    admin = admin_client(client, make_user)
    admin_id = admin.get("/api/auth/me").json()["id"]
    self_response = admin.post(f"/api/auth/users/{admin_id}/deactivate")
    assert self_response.status_code == 403
    demote = admin.patch(f"/api/auth/users/{admin_id}", json={"role": "manager"})
    assert demote.status_code == 403


def test_disabled_admin_can_be_edited_while_one_admin_is_active(client, make_user):
    disabled = make_user("admin_old", role="admin", email="old@example.com", is_active=False)
    admin = admin_client(client, make_user)
    rename = admin.patch(f"/api/auth/users/{disabled.id}", json={"full_name": "Old Admin"})
    assert rename.status_code == 200, rename.text
    demote = admin.patch(f"/api/auth/users/{disabled.id}", json={"role": "manager"})
    assert demote.status_code == 200, demote.text
    assert admin.post(f"/api/auth/users/{disabled.id}/deactivate").status_code == 200


def test_admin_unlocks_a_locked_account(client, make_user, db):
    target = make_user("manager_locked", role="manager", email="locked@example.com")
    target_client = TestClient(client.app)
    for _ in range(5):
        assert login(target_client, "manager_locked", "wrong-password").status_code == 401
    assert login(target_client, "manager_locked").status_code == 423

    admin = admin_client(client, make_user)
    listed = admin.get("/api/auth/users").json()["users"]
    assert next(u for u in listed if u["id"] == target.id)["is_locked"] is True
    unlocked = admin.post(f"/api/auth/users/{target.id}/unlock")
    assert unlocked.status_code == 200, unlocked.text
    assert unlocked.json()["is_locked"] is False
    assert "user_unlocked" in conn_actions(db)
    assert login(target_client, "manager_locked").status_code == 200

    make_user("manager_other", role="manager", email="other@example.com")
    assert login(client, "manager_other").status_code == 200
    assert client.post(f"/api/auth/users/{target.id}/unlock").status_code == 403
