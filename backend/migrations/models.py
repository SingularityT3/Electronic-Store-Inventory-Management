"""Imports every module's tables so `metadata` describes the whole schema.

Used by Alembic, the seed script and the schema tests. It lives outside `app`, so it may
import module internals without breaking the import-linter contracts.
"""

import app.modules.audit._internal.models
import app.modules.auth._internal.models
import app.modules.notifications._internal.models
import app.modules.product._internal.models
import app.modules.purchasing._internal.models
import app.modules.sales._internal.models
import app.modules.stock._internal.models  # noqa: F401
from app.db import Base

metadata = Base.metadata
