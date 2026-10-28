"""CSRF protection on state-changing requests (SEC-SES-4)."""

from app.modules.auth._internal.csrf import CSRF_COOKIE, CSRF_HEADER
from tests.helpers import login
from tests.test_products import category, product_payload


def test_login_sets_a_csrf_cookie_the_page_can_read(client, make_user):
    make_user("manager_csrf", role="manager")
    response = login(client, "manager_csrf")
    cookie = next(c for c in response.headers.get_list("set-cookie") if CSRF_COOKIE in c)
    assert "httponly" not in cookie.lower()
    assert "samesite=strict" in cookie.lower()


def test_sec_ses_4_it_1_request_without_token_is_rejected(client, plain_client, db, make_user):
    make_user("manager_csrf", role="manager")
    cat = category(db)
    login(plain_client, "manager_csrf")
    before = plain_client.get("/api/product").json()

    missing = plain_client.post("/api/product", json=product_payload(cat.id))
    wrong = plain_client.post(
        "/api/product", json=product_payload(cat.id), headers={CSRF_HEADER: "forged"}
    )

    assert missing.status_code == 403
    assert wrong.status_code == 403
    assert plain_client.get("/api/product").json() == before


def test_sec_ses_4_it_2_request_with_token_succeeds(client, db, make_user):
    make_user("manager_csrf", role="manager")
    cat = category(db)
    login(client, "manager_csrf")

    response = client.post("/api/product", json=product_payload(cat.id))

    assert response.status_code == 201


def test_safe_requests_and_public_posts_need_no_token(plain_client, make_user):
    make_user("manager_csrf", role="manager")
    assert login(plain_client, "manager_csrf").status_code == 200
    assert plain_client.get("/api/auth/me").status_code == 200
    assert plain_client.post("/api/auth/logout").status_code == 204
