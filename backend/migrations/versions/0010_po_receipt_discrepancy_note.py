"""Store receipt discrepancy notes per PO line."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("po_receipt_lines", sa.Column("discrepancy_note", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("po_receipt_lines", "discrepancy_note")
