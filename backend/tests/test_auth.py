"""Authentication: login, lockout, sessions, logout and password reset (#5).

Test plan cases FR5.2-UT-1..3, FR5.2-IT-1, FR5.2-IT-3, FR5.2-ST-1 and FR5.2-ST-2.
"""

from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any

import pytest
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_session
from app.main import app
from app.modules.auth import current_user
from app.modules.auth._internal.models import User
from app.modules.auth._internal.passwords import hash_password

PASSWORD = "correct-horse-battery"
GENERIC_ERROR = "Invalid username or password"
SETTINGS = Settings(cookie_secure=False, app_base_url="http://esims.test")


@pytest.fixture
def db(conn: Connection) -> Iterator[Session]:
    """An ORM session in the test's transaction; commits become savepoints."""
    with Session(bind=conn, join_transaction_mode="create_savepoint") as session:
        yield session


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_session] = lambda: db
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def make_user(db: Session):
    def make(username: str = "cashier_ravi", **fields: Any) -> User:
        user = User(
            username=username,
            full_name="Ravi Kumar",
            password_hash=hash_password(PASSWORD),
            role="manager",
            **fields,
        )
        db.add(user)
        db.commit()
        return user

    return make


def login(client: TestClient, username: str = "cashier_ravi", password: str = PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def audit_actions(conn: Connection) -> list[str]:
    return list(conn.execute(text("SELECT action FROM audit_log ORDER BY id")).scalars())


# FR5.2-UT-1
def test_valid_credentials_log_in(client, make_user, conn):
    user = make_user()
    response = login(client)
    assert response.status_code == 200
    assert response.json() == {
        "id": user.id,
        "username": "cashier_ravi",
        "full_name": "Ravi Kumar",
        "role": "manager",
        "location_id": None,
    }
    assert client.get("/api/auth/me").json()["id"] == user.id
    assert audit_actions(conn) == ["login"]


def test_login_by_email_and_any_case(client, make_user):
    make_user(email="ravi@example.com")
    assert login(client, "RAVI@example.com").status_code == 200
    assert login(client, "Cashier_Ravi").status_code == 200


def test_session_cookie_is_httponly_secure_samesite(client, make_user):
    make_user()
    app.dependency_overrides[get_settings] = lambda: Settings(cookie_secure=True)
    cookie = login(client).headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=strict" in cookie


# FR5.2-UT-2
@pytest.mark.parametrize("username", ["cashier_ravi", "nobody"])
def test_invalid_credentials_get_generic_error(client, make_user, conn, username):
    make_user()
    response = login(client, username, "wrongpass123")
    assert response.status_code == 401
    assert response.json() == {"detail": GENERIC_ERROR}
    assert "set-cookie" not in response.headers
    entry = conn.execute(text("SELECT action, username, details FROM audit_log")).one()
    assert entry.action == "login_failed"
    assert entry.username == username
    assert "wrongpass123" not in (entry.details or "")


PUBLIC_ROUTES = {
    "/api/health",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/password-reset/request",
    "/api/auth/password-reset/confirm",
}


def depends_on(dependant: Dependant, call: Callable[..., Any]) -> bool:
    return any(d.call is call or depends_on(d, call) for d in dependant.dependencies)


# FR5.2-UT-3, SEC-AUTH-1
def test_every_non_public_route_requires_a_session():
    routes = [r for r in app.routes if isinstance(r, APIRoute)]
    assert {r.path for r in routes} >= PUBLIC_ROUTES
    for route in routes:
        if route.path not in PUBLIC_ROUTES:
            assert depends_on(route.dependant, current_user), route.path


def test_protected_endpoint_without_session_gets_401(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/health").status_code == 200


def test_forged_session_cookie_is_rejected(client):
    client.cookies.set("esims_session", "made-up-token")
    assert client.get("/api/auth/me").status_code == 401


# FR5.2-ST-2
def test_lockout_after_five_failures_blocks_correct_password(client, make_user, db, conn):
    user = make_user()
    for _ in range(4):
        assert login(client, password="wrong").status_code == 401
    response = login(client, password="wrong")
    assert response.json() == {"detail": GENERIC_ERROR}

    response = login(client)
    assert response.status_code == 423
    assert "locked" in response.json()["detail"]
    # A wrong password while locked stays generic and does not extend the lockout.
    db.refresh(user)
    locked_until = user.locked_until
    assert login(client, password="wrong").json() == {"detail": GENERIC_ERROR}
    db.refresh(user)
    assert user.locked_until == locked_until

    assert "account_locked" in audit_actions(conn)

    # After the lockout period the correct password works again.
    user.locked_until = locked_until - timedelta(minutes=16)
    db.commit()
    assert login(client).status_code == 200


def test_admin_unlock_clears_lockout(client, make_user, db):
    user = make_user()
    for _ in range(5):
        login(client, password="wrong")
    assert login(client).status_code == 423
    user.locked_until = None  # what an Admin unlock (#7) does
    db.commit()
    assert login(client).status_code == 200


def test_success_resets_failure_count(client, make_user, db):
    user = make_user()
    for _ in range(4):
        login(client, password="wrong")
    assert login(client).status_code == 200
    db.refresh(user)
    assert user.failed_login_count == 0
    for _ in range(4):
        login(client, password="wrong")
    assert login(client).status_code == 200


def test_disabled_account_gets_status_message(client, make_user):
    make_user(is_active=False)
    response = login(client)
    assert response.status_code == 403
    assert "disabled" in response.json()["detail"]
    assert login(client, password="wrong").json() == {"detail": GENERIC_ERROR}


def test_deactivation_ends_active_sessions(client, make_user, db):
    user = make_user()
    login(client)
    user.is_active = False
    db.commit()
    assert client.get("/api/auth/me").status_code == 401


# FR5.2-IT-1
def test_idle_session_expires(client, make_user, conn):
    make_user()
    login(client)
    conn.execute(text("UPDATE user_sessions SET last_seen_at = now() - interval '31 minutes'"))
    assert client.get("/api/auth/me").status_code == 401
    # The expired session is gone, so it cannot be revived.
    assert conn.execute(text("SELECT count(*) FROM user_sessions")).scalar_one() == 0


def test_activity_keeps_session_alive(client, make_user, conn):
    make_user()
    login(client)
    conn.execute(text("UPDATE user_sessions SET last_seen_at = now() - interval '29 minutes'"))
    assert client.get("/api/auth/me").status_code == 200
    seen = conn.execute(text("SELECT now() - last_seen_at FROM user_sessions")).scalar_one()
    assert seen < timedelta(minutes=1)


def test_session_expires_after_absolute_lifetime(client, make_user, conn):
    make_user()
    login(client)
    conn.execute(text("UPDATE user_sessions SET expires_at = now() - interval '1 second'"))
    assert client.get("/api/auth/me").status_code == 401


def test_timeouts_are_configurable(client, make_user, conn):
    make_user()
    app.dependency_overrides[get_settings] = lambda: Settings(
        cookie_secure=False, session_idle_minutes=5
    )
    login(client)
    conn.execute(text("UPDATE user_sessions SET last_seen_at = now() - interval '6 minutes'"))
    assert client.get("/api/auth/me").status_code == 401


# FR5.2-ST-1 (session part; role checks are #6)
def test_logout_invalidates_session_on_server(client, make_user, conn):
    make_user()
    login(client)
    token = client.cookies["esims_session"]
    response = client.post("/api/auth/logout")
    assert response.status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    # Replaying the old cookie does not work either.
    client.cookies.set("esims_session", token)
    assert client.get("/api/auth/me").status_code == 401
    assert audit_actions(conn) == ["login", "logout"]


def test_api_responses_are_not_cached(client, make_user):
    make_user()
    login(client)
    assert client.get("/api/auth/me").headers["cache-control"] == "no-store"


# FR5.2-IT-3
def test_passwords_are_stored_as_salted_hashes(make_user, db):
    first = make_user("user_one")
    second = make_user("user_two")
    for user in (first, second):
        assert user.password_hash.startswith("$argon2id$")
        assert PASSWORD not in user.password_hash
    assert first.password_hash != second.password_hash  # salted


@pytest.fixture
def sent_emails(monkeypatch) -> list[tuple[str, str]]:
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.modules.auth.router.send_reset_email",
        lambda settings, to, link: sent.append((to, link)),
    )
    return sent


def reset_token(link: str) -> str:
    return link.split("token=", 1)[1]


def test_password_reset_flow(client, make_user, sent_emails, conn):
    user = make_user(email="ravi@example.com")
    old_hash = user.password_hash
    login(client)

    response = client.post("/api/auth/password-reset/request", json={"username": "cashier_ravi"})
    assert response.status_code == 202
    [(to, link)] = sent_emails
    assert to == "ravi@example.com"
    assert link.startswith("http://esims.test/reset-password?token=")
    assert PASSWORD not in link and old_hash not in link

    response = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": reset_token(link), "new_password": "a-new-password"},
    )
    assert response.status_code == 204
    # Existing sessions end, the old password stops working and the new one works.
    assert client.get("/api/auth/me").status_code == 401
    assert login(client).status_code == 401
    assert login(client, password="a-new-password").status_code == 200
    assert "password_reset" in audit_actions(conn)


def test_reset_request_does_not_reveal_accounts(client, make_user, sent_emails):
    make_user()  # no email address
    known = client.post("/api/auth/password-reset/request", json={"username": "cashier_ravi"})
    unknown = client.post("/api/auth/password-reset/request", json={"username": "nobody"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert sent_emails == []


def test_reset_token_is_single_use(client, make_user, sent_emails):
    make_user(email="ravi@example.com")
    client.post("/api/auth/password-reset/request", json={"username": "cashier_ravi"})
    token = reset_token(sent_emails[0][1])
    body = {"token": token, "new_password": "a-new-password"}
    assert client.post("/api/auth/password-reset/confirm", json=body).status_code == 204
    assert client.post("/api/auth/password-reset/confirm", json=body).status_code == 400


def test_reset_token_expires(client, make_user, sent_emails, conn):
    make_user(email="ravi@example.com")
    client.post("/api/auth/password-reset/request", json={"username": "cashier_ravi"})
    conn.execute(text("UPDATE password_reset_tokens SET expires_at = now() - interval '1 second'"))
    body = {"token": reset_token(sent_emails[0][1]), "new_password": "a-new-password"}
    response = client.post("/api/auth/password-reset/confirm", json=body)
    assert response.status_code == 400
    assert login(client).status_code == 200


def test_new_reset_link_spends_older_ones_when_used(client, make_user, sent_emails):
    make_user(email="ravi@example.com")
    for _ in range(2):
        client.post("/api/auth/password-reset/request", json={"username": "cashier_ravi"})
    first, second = (reset_token(link) for _, link in sent_emails)
    body = {"token": second, "new_password": "a-new-password"}
    assert client.post("/api/auth/password-reset/confirm", json=body).status_code == 204
    body = {"token": first, "new_password": "another-password"}
    assert client.post("/api/auth/password-reset/confirm", json=body).status_code == 400
