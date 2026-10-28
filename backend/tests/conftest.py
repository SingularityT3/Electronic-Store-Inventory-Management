"""Database fixtures. Tests that use them need the compose `db` service running.

Each fixture works on a throwaway database created next to the one in DATABASE_URL,
so tests never touch development data.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import URL, Connection, Engine, create_engine, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import database_url, get_session
from app.main import app
from app.modules.auth._internal.models import User
from app.modules.auth._internal.passwords import hash_password
from tests.helpers import PASSWORD, SETTINGS, CsrfClient

BACKEND_DIR = Path(__file__).resolve().parent.parent


def alembic_config(url: URL) -> Config:
    config = Config(BACKEND_DIR / "alembic.ini")
    # configparser treats % as interpolation, so escape it in the password.
    config.set_main_option(
        "sqlalchemy.url", url.render_as_string(hide_password=False).replace("%", "%%")
    )
    config.attributes["configure_logger"] = False
    return config


@contextmanager
def throwaway_database() -> Iterator[URL]:
    """Create an empty database, yield its URL, then drop it."""
    server_url = database_url()
    name = f"esims_test_{uuid.uuid4().hex[:12]}"
    admin = create_engine(server_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield server_url.set(database=name)
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
def empty_db_url() -> Iterator[URL]:
    with throwaway_database() as url:
        yield url


@pytest.fixture(scope="session")
def migrated_engine() -> Iterator[Engine]:
    """An engine on a database migrated to head, shared by the whole session."""
    with throwaway_database() as url:
        command.upgrade(alembic_config(url), "head")
        engine = create_engine(url)
        yield engine
        engine.dispose()


@pytest.fixture
def conn(migrated_engine: Engine) -> Iterator[Connection]:
    """A connection inside a transaction that is rolled back after the test."""
    with migrated_engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()


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
        yield CsrfClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def plain_client(client: TestClient) -> TestClient:
    """A client that, like a page on another site, never sends the CSRF header."""
    return TestClient(client.app)


@pytest.fixture
def make_user(db: Session):
    def make(username: str = "cashier_ravi", **fields: Any) -> User:
        fields.setdefault("role", "manager")
        user = User(
            username=username,
            full_name="Ravi Kumar",
            password_hash=hash_password(PASSWORD),
            **fields,
        )
        db.add(user)
        db.commit()
        return user

    return make
