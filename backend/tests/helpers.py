"""Constants and helpers shared by the API tests."""

from fastapi.testclient import TestClient

from app.config import Settings

CSRF_COOKIE = "esims_csrf"
CSRF_HEADER = "X-CSRF-Token"
PASSWORD = "correct-horse-battery"
SETTINGS = Settings(cookie_secure=False, app_base_url="http://esims.test")


def login(client: TestClient, username: str = "cashier_ravi", password: str = PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})


class CsrfClient(TestClient):
    """A test client that behaves like the web app: it echoes the CSRF cookie in the header."""

    def request(self, method, url, **kwargs):  # type: ignore[no-untyped-def]
        token = self.cookies.get(CSRF_COOKIE)
        if token and method.upper() not in ("GET", "HEAD", "OPTIONS"):
            kwargs["headers"] = {CSRF_HEADER: token, **(kwargs.get("headers") or {})}
        return super().request(method, url, **kwargs)
