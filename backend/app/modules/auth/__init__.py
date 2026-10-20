"""Authentication, sessions, users and roles (RBAC).

Public surface of the `auth` module. Other modules may import from here only;
`_internal` is private to this module.
"""

from app.modules.auth._internal.dependencies import current_user
from app.modules.auth.service import AuthService, CurrentUser

__all__ = ["AuthService", "CurrentUser", "current_user"]
