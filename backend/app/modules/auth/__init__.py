"""Authentication, sessions, users and roles (RBAC).

Public surface of the `auth` module. Other modules may import from here only;
`_internal` is private to this module.
"""

from app.modules.auth._internal.dependencies import current_user
from app.modules.auth._internal.permissions import (
    authorize,
    authorize_location,
    ensure_routes_authorized,
    has_permission,
    require,
    signed_in,
)
from app.modules.auth.service import (
    AuthService,
    CurrentUser,
    Permission,
    po_status_notification_recipients,
)

__all__ = [
    "AuthService",
    "CurrentUser",
    "Permission",
    "po_status_notification_recipients",
    "authorize",
    "authorize_location",
    "current_user",
    "ensure_routes_authorized",
    "has_permission",
    "require",
    "signed_in",
]
