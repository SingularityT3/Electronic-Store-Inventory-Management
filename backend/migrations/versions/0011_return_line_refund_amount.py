"""Add refund_amount to return_lines."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "return_lines",
        sa.Column(
            "refund_amount",
            sa.Numeric(12, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_return_lines_refund_amount_non_negative"),
        "return_lines",
        "refund_amount >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_return_lines_refund_amount_non_negative"),
        "return_lines",
        type_="check",
    )
    op.drop_column("return_lines", "refund_amount")
