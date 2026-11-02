"""The first-Admin command for a new installation (scripts/create_admin.py, #40)."""

from collections.abc import Iterator

import pytest
from alembic import command
from sqlalchemy import Engine, create_engine, text

from app.modules.auth._internal.passwords import verify_password
from scripts.create_admin import CreateAdminError, create_admin
from tests.conftest import alembic_config, throwaway_database

PASSWORD = "first-admin-password"


@pytest.fixture
def fresh_engine() -> Iterator[Engine]:
    """An empty, migrated database of its own: the command commits."""
    with throwaway_database() as url:
        command.upgrade(alembic_config(url), "head")
        engine = create_engine(url)
        yield engine
        engine.dispose()


def test_creates_an_active_admin_with_a_hashed_password_and_an_audit_entry(fresh_engine):
    user_id = create_admin(
        fresh_engine,
        username=" owner ",
        full_name="Store Owner",
        email="Owner@Example.com",
        password=PASSWORD,
    )

    with fresh_engine.connect() as conn:
        row = conn.execute(
            text("SELECT username, email, role, is_active, password_hash FROM users WHERE id=:id"),
            {"id": user_id},
        ).one()
        audit = conn.execute(
            text("SELECT username, action, entity_id FROM audit_log WHERE action='user_created'")
        ).one()
    assert (row.username, row.email, row.role, row.is_active) == (
        "owner",
        "owner@example.com",
        "admin",
        True,
    )
    assert PASSWORD not in row.password_hash
    assert verify_password(row.password_hash, PASSWORD)
    assert tuple(audit) == ("system", "user_created", str(user_id))


def test_the_new_admin_can_sign_in_and_open_user_management(fresh_engine):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from app.config import get_settings
    from app.db import get_session
    from app.main import app
    from tests.helpers import SETTINGS, CsrfClient

    create_admin(fresh_engine, username="owner", full_name="Store Owner", password=PASSWORD)
    with Session(fresh_engine) as session:
        app.dependency_overrides[get_session] = lambda: session
        app.dependency_overrides[get_settings] = lambda: SETTINGS
        try:
            client: TestClient = CsrfClient(app)
            login = client.post("/api/auth/login", json={"username": "owner", "password": PASSWORD})
            assert login.status_code == 200, login.text
            assert client.get("/api/auth/users").status_code == 200
        finally:
            app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"username": "OWNER"}, "already exists"),
        ({"username": "other", "email": "OWNER@example.com"}, "email"),
        ({"username": "other", "password": "short"}, "at least 8"),
        ({"username": " ", "full_name": "x"}, "required"),
    ],
)
def test_refuses_duplicates_short_passwords_and_blanks(fresh_engine, fields, message):
    create_admin(
        fresh_engine,
        username="owner",
        full_name="Store Owner",
        email="owner@example.com",
        password=PASSWORD,
    )
    arguments = {"full_name": "Someone", "password": PASSWORD, **fields}
    with pytest.raises(CreateAdminError, match=message):
        create_admin(fresh_engine, **arguments)


def test_set_password_replaces_the_password_ends_sessions_and_clears_lockout(fresh_engine):
    from datetime import UTC, datetime, timedelta

    from scripts.set_password import SetPasswordError, set_password

    user_id = create_admin(fresh_engine, username="clerk", full_name="Clerk", password=PASSWORD)
    with fresh_engine.begin() as conn:
        conn.execute(
            text("UPDATE users SET failed_login_count=5, locked_until=:until WHERE id=:id"),
            {"until": datetime.now(UTC) + timedelta(minutes=15), "id": user_id},
        )
        conn.execute(
            text(
                "INSERT INTO user_sessions (token_hash, user_id, expires_at) "
                "VALUES ('x' || :id, :id, now() + interval '1 hour')"
            ),
            {"id": user_id},
        )

    set_password(fresh_engine, username="CLERK", password="a-new-password")

    with fresh_engine.connect() as conn:
        row = conn.execute(
            text("SELECT password_hash, failed_login_count, locked_until FROM users WHERE id=:id"),
            {"id": user_id},
        ).one()
        sessions = conn.execute(
            text("SELECT count(*) FROM user_sessions WHERE user_id=:id"), {"id": user_id}
        ).scalar_one()
        audited = conn.execute(
            text("SELECT count(*) FROM audit_log WHERE action='password_set_by_operator'")
        ).scalar_one()
    assert verify_password(row.password_hash, "a-new-password")
    assert not verify_password(row.password_hash, PASSWORD)
    assert (row.failed_login_count, row.locked_until, sessions, audited) == (0, None, 0, 1)
    with pytest.raises(SetPasswordError, match="No user"):
        set_password(fresh_engine, username="nobody", password="a-new-password")
    with pytest.raises(SetPasswordError, match="at least 8"):
        set_password(fresh_engine, username="clerk", password="short")
