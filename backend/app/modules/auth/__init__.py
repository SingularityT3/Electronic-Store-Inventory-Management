"""Authentication, sessions, users and roles (RBAC).

Public surface of the `auth` module. Other modules may import from here only;
`_internal` is private to this module.
"""

from app.modules.auth.service import AuthService

__all__ = ["AuthService"]
