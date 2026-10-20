"""Read-only reports and exports built on other modules' services.

Public surface of the `reporting` module. Other modules may import from here only;
`_internal` is private to this module.
"""

from app.modules.reporting.service import ReportingService

__all__ = ["ReportingService"]
