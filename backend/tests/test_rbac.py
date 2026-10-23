"""Role-based access control (#6).

Test plan cases FR5.1-UT-2, FR5.1-UT-3, FR5.1-IT-1..3, FR5.1-ST-1, FR5.2-IT-2 and FR5.3-IT-3.
Feature routes arrive with later issues, so these tests mount one probe route per permission
on a fresh app and check every role against it.
"""

from collections.abc import Iterator
from typing import Annotated

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import Connection, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.main import PUBLIC_PATHS, create_app
from app.modules.audit import audit_service
from app.modules.auth import (
    CurrentUser,
    Permission,
    authorize,
    authorize_location,
    ensure_routes_authorized,
    require,
)
from app.modules.auth._internal.permissions import ROLE_PERMISSIONS
from tests.helpers import SETTINGS, login

P = Permission
ROLES = ("admin", "manager", "staff", "cashier")

# The matrix from issue #6 (SRS 2.3, A-5, A-6, A-9, A-10), written out independently of
# ROLE_PERMISSIONS so a change to either one fails the tests. Order: Admin, Manager, Staff,
# Cashier.
EXPECTED = {
    P.USERS_MANAGE: "Y...",
    P.AUDIT_VIEW: "Y...",
    P.PRODUCTS_VIEW: "YYYY",
    P.PRODUCTS_MANAGE: "YY..",
    P.STOCK_VIEW: "YYY.",
    P.LOCATIONS_MANAGE: "YY..",
    P.STOCK_ADJUST: "YYY.",
    P.STOCK_TRANSFER: "YYY.",
    P.SUPPLIERS_MANAGE: "YY..",
    P.PURCHASE_ORDERS_MANAGE: "YY..",
    P.PURCHASE_ORDERS_RECEIVE: "YYY.",
    P.SALES_RECORD: "YY.Y",
    P.RETURNS_APPROVE_LATE: "YY..",
    P.REPORTS_VIEW: "YY..",
    P.NOTIFICATIONS_VIEW: "YYY.",
}


def allowed(role: str, permission: Permission) -> bool:
    return EXPECTED[permission][ROLES.index(role)] == "Y"


class ProductEdit(BaseModel):
    name: str | None = None
    price: str | None = None


def probe_router() -> APIRouter:
    router = APIRouter(prefix="/api/probe")

    def ok() -> dict[str, str]:
        return {"status": "ok"}

    for permission in Permission:
        router.add_api_route(
            f"/{permission}", ok, methods=["GET"], dependencies=[Depends(require(permission))]
        )

    @router.patch("/products/1")
    def edit_product(
        body: ProductEdit,
        user: Annotated[CurrentUser, Depends(require(P.PRODUCTS_VIEW))],
        db: Annotated[Session, Depends(get_session)],
    ) -> dict[str, str]:
        # Stand-in for a change the route makes before it reaches the price check.
        audit_service.record(db, module="product", action="product_updated")
        if body.price is not None:
            authorize(db, user, P.PRODUCTS_MANAGE, "Edit price of product 1")
        db.commit()
        return {"status": "ok"}

    @router.get("/locations/{location_id}/stock")
    def location_stock(
        location_id: int,
        user: Annotated[CurrentUser, Depends(require(P.STOCK_VIEW))],
        db: Annotated[Session, Depends(get_session)],
    ) -> dict[str, str]:
        authorize_location(db, user, location_id, "View stock")
        return {"status": "ok"}

    return router


@pytest.fixture
def probe_app(db: Session) -> Iterator[FastAPI]:
    app = create_app()
    app.include_router(probe_router())
    ensure_routes_authorized(app.routes, PUBLIC_PATHS)
    app.dependency_overrides[get_session] = lambda: db
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    yield app


@pytest.fixture
def signed_in_as(probe_app: FastAPI, make_user):
    """Sign in a new user with `role` and return their client."""

    def sign_in(role: str, location_id: int | None = 1) -> TestClient:
        client = TestClient(probe_app)
        make_user(f"{role}_user", role=role, location_id=location_id)
        assert login(client, f"{role}_user").status_code == 200
        return client

    return sign_in


def audit_entries(conn: Connection):
    return conn.execute(
        text("SELECT action, username, details, occurred_at FROM audit_log ORDER BY id")
    ).all()


def test_role_permissions_match_the_matrix():
    for role in ROLES:
        assert ROLE_PERMISSIONS[role] == {p for p in Permission if allowed(role, p)}, role


# FR5.1-ST-1, FR5.1-UT-2, FR5.1-UT-3, FR5.1-IT-2, SEC-AZ-2
@pytest.mark.parametrize("role", ROLES)
def test_api_enforces_the_matrix_for_every_role(signed_in_as, role):
    client = signed_in_as(role)
    for permission in Permission:
        response = client.get(f"/api/probe/{permission}")
        expected = 200 if allowed(role, permission) else 403
        assert response.status_code == expected, (role, permission)


def test_signed_out_requests_get_401_not_403(probe_app):
    assert TestClient(probe_app).get(f"/api/probe/{P.PRODUCTS_VIEW}").status_code == 401


# FR5.3-IT-3, SEC-AUD-1
def test_denied_attempt_is_audited(signed_in_as, conn):
    client = signed_in_as("cashier")
    response = client.get(f"/api/probe/{P.PRODUCTS_MANAGE}")
    assert response.status_code == 403
    assert response.json() == {"detail": "You do not have permission to do this."}
    entry = audit_entries(conn)[-1]
    assert entry.action == "unauthorized_access_attempt"
    assert entry.username == "cashier_user"
    assert entry.occurred_at is not None
    assert entry.details.startswith("Unauthorized Access Attempt: GET /api/probe/products.manage")


def test_allowed_request_is_not_audited_as_denied(signed_in_as, conn):
    client = signed_in_as("cashier")
    assert client.get(f"/api/probe/{P.SALES_RECORD}").status_code == 200
    assert [e.action for e in audit_entries(conn)] == ["login"]


# FR5.1-IT-1
def test_role_change_applies_to_the_next_request(signed_in_as, db):
    client = signed_in_as("staff")
    assert client.get(f"/api/probe/{P.REPORTS_VIEW}").status_code == 403
    db.execute(text("UPDATE users SET role = 'manager' WHERE username = 'staff_user'"))
    db.commit()
    assert client.get(f"/api/probe/{P.REPORTS_VIEW}").status_code == 200
    assert P.REPORTS_VIEW in client.get("/api/auth/me").json()["permissions"]


# FR5.1-IT-3: the menu is built from these, so it shows what the role may do and no more.
@pytest.mark.parametrize("role", ROLES)
def test_me_lists_the_role_permissions(signed_in_as, role):
    permissions = signed_in_as(role).get("/api/auth/me").json()["permissions"]
    assert set(permissions) == {p for p in Permission if allowed(role, p)}


# FR5.2-IT-2
def test_per_action_check_within_a_screen(signed_in_as, conn):
    staff = signed_in_as("staff")
    assert staff.get(f"/api/probe/{P.PRODUCTS_VIEW}").status_code == 200
    assert staff.patch("/api/probe/products/1", json={"name": "TV"}).status_code == 200
    assert staff.patch("/api/probe/products/1", json={"price": "999"}).status_code == 403
    # The denied request's own changes are discarded; only the denial is recorded.
    assert [e.action for e in audit_entries(conn)] == [
        "login",
        "product_updated",
        "unauthorized_access_attempt",
    ]
    assert "Edit price of product 1" in audit_entries(conn)[-1].details

    manager = signed_in_as("manager", location_id=None)
    assert manager.patch("/api/probe/products/1", json={"price": "999"}).status_code == 200


# SRS A-9, SEC-AZ-7
def test_staff_see_only_their_own_location(signed_in_as):
    staff = signed_in_as("staff", location_id=1)
    assert staff.get("/api/probe/locations/1/stock").status_code == 200
    assert staff.get("/api/probe/locations/2/stock").status_code == 403
    manager = signed_in_as("manager", location_id=None)
    assert manager.get("/api/probe/locations/2/stock").status_code == 200


# SEC-AZ-1: deny by default
def test_app_refuses_to_start_with_an_unguarded_route():
    app = create_app()

    @app.get("/api/product/unguarded")
    def unguarded() -> None: ...

    with pytest.raises(RuntimeError, match="/api/product/unguarded"):
        ensure_routes_authorized(app.routes, PUBLIC_PATHS)


def test_require_needs_a_permission():
    with pytest.raises(ValueError):
        require()
