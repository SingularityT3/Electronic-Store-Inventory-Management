"""Add expected delivery date to purchase orders."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "purchase_orders",
        sa.Column("expected_delivery_date", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("purchase_orders", "expected_delivery_date")
