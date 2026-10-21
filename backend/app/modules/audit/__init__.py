"""Immutable audit log.

Public surface of the `audit` module. Other modules may import from here only;
`_internal` is private to this module.
"""

from app.modules.audit._internal.service import DbAuditService, changes
from app.modules.audit.service import (
    AuditEntry,
    AuditFilter,
    AuditFilterOptions,
    AuditPage,
    AuditService,
)

audit_service: AuditService = DbAuditService()

__all__ = [
    "AuditEntry",
    "AuditFilter",
    "AuditFilterOptions",
    "AuditPage",
    "AuditService",
    "audit_service",
    "changes",
]
