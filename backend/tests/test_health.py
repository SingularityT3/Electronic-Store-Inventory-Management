from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.db import get_session
from app.main import app


class FakeSession:
    def __init__(self, fail: bool):
        self.fail = fail

    def execute(self, statement):
        if self.fail:
            raise RuntimeError("connection refused")


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health_returns_ok(client):
    app.dependency_overrides[get_session] = lambda: FakeSession(fail=False)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "ok"}}


def test_health_is_unhealthy_when_database_is_down(client):
    app.dependency_overrides[get_session] = lambda: FakeSession(fail=True)
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json() == {"status": "unhealthy", "checks": {"database": "error"}}
