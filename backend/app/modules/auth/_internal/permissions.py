"""Role-based access control (FR-5.1, NFR-7, SEC-AZ-1, SEC-AZ-2, SEC-AZ-7).

Every route declares what it needs with `require(...)` (or `signed_in` for self-service
routes such as `/auth/me`), and `ensure_routes_authorized` refuses to start the app if a
non-public route declares nothing, so access is denied by default. The role is read from the
database on every request, so a role change applies to the user's next request.
"""

from collections.abc import Iterable
from typing import Annotated, NoReturn

from fastapi import Depends, HTTPException, Request, status
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session

from app.db import get_session
from app.modules.audit import audit_service
from app.modules.auth._internal.dependencies import current_user
from app.modules.auth._internal.models import ROLES
from app.modules.auth.service import CurrentUser, Permission

P = Permission

# SRS 2.3, A-5, A-6, A-9, A-10 and the use case actors. Anything not listed is denied.
ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "admin": frozenset(Permission),
    "manager": frozenset(Permission) - {P.USERS_MANAGE, P.AUDIT_VIEW},
    "staff": frozenset(
        {
            P.PRODUCTS_VIEW,
            P.STOCK_VIEW,
            P.STOCK_ADJUST,
            P.STOCK_TRANSFER,
            P.PURCHASE_ORDERS_RECEIVE,
            P.NOTIFICATIONS_VIEW,
        }
    ),
    "cashier": frozenset({P.PRODUCTS_VIEW, P.SALES_RECORD}),
}
assert ROLE_PERMISSIONS.keys() == ROLES.keys()

FORBIDDEN = "You do not have permission to do this."
UNAUTHORIZED_ACTION = "unauthorized_access_attempt"


def has_permission(role: str, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, frozenset())


def permissions_for(role: str) -> list[Permission]:
    return sorted(ROLE_PERMISSIONS.get(role, frozenset()))


def deny(db: Session, user: CurrentUser, attempted: str) -> NoReturn:
    """Log an "Unauthorized Access Attempt" (FR-5.3, SEC-AUD-1) and respond 403.

    Discards whatever the request changed so far, so only the audit entry is committed.
    """
    db.rollback()
    audit_service.record(
        db,
        module="auth",
        action=UNAUTHORIZED_ACTION,
        user_id=user.id,
        username=user.username,
        entity_type="user",
        entity_id=str(user.id),
        details=f"Unauthorized Access Attempt: {attempted} (role {user.role})",
    )
    db.commit()
    raise HTTPException(status.HTTP_403_FORBIDDEN, FORBIDDEN)


def authorize(db: Session, user: CurrentUser, permission: Permission, attempted: str) -> None:
    """Per-action check inside a route (FR-5.2-IT-2), e.g. a price change on a product edit."""
    if not has_permission(user.role, permission):
        deny(db, user, f"{attempted} needs {permission}")


def authorize_location(db: Session, user: CurrentUser, location_id: int, attempted: str) -> None:
    """Record-level scoping (SRS A-9, SEC-AZ-7): Staff and Cashier act on their location only."""
    if not user.sees_all_locations and user.location_id != location_id:
        deny(db, user, f"{attempted} at location {location_id}")


class PermissionCheck:
    """Dependency that lets the request through only if the user's role has every permission.

    With no permissions it admits any signed-in user.
    """

    def __init__(self, *permissions: Permission) -> None:
        self.permissions = permissions

    def __call__(
        self,
        request: Request,
        user: Annotated[CurrentUser, Depends(current_user)],
        db: Annotated[Session, Depends(get_session)],
    ) -> CurrentUser:
        missing = [p for p in self.permissions if not has_permission(user.role, p)]
        if missing:
            deny(db, user, f"{request.method} {request.url.path} needs {', '.join(missing)}")
        return user

    def __repr__(self) -> str:
        return f"require({', '.join(self.permissions)})"


def require(*permissions: Permission) -> PermissionCheck:
    """`Depends(require(Permission.X))` on a route or router: 403 unless the role has X."""
    if not permissions:
        raise ValueError("require() needs a permission; use `signed_in` for any signed-in user")
    return PermissionCheck(*permissions)


signed_in = PermissionCheck()
"""Any signed-in user, whatever the role. For self-service routes such as `/auth/me`."""


def _declares_access(dependant: Dependant) -> bool:
    return any(
        isinstance(d.call, PermissionCheck) or _declares_access(d) for d in dependant.dependencies
    )


def ensure_routes_authorized(routes: Iterable[object], public_paths: set[str]) -> None:
    """Fail at startup if a non-public route has no `require(...)` or `signed_in` (deny by
    default, SEC-AZ-1)."""
    unguarded = sorted(
        route.path
        for route in routes
        if isinstance(route, APIRoute)
        and route.path not in public_paths
        and not _declares_access(route.dependant)
    )
    if unguarded:
        raise RuntimeError(f"Routes without a permission check: {', '.join(unguarded)}")
