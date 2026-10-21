"""Constants and helpers shared by the API tests."""

from fastapi.testclient import TestClient

from app.config import Settings

PASSWORD = "correct-horse-battery"
SETTINGS = Settings(cookie_secure=False, app_base_url="http://esims.test")


def login(client: TestClient, username: str = "cashier_ravi", password: str = PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})
