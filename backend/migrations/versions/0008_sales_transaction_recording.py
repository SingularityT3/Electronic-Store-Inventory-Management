"""Add sale discounts and idempotency keys."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sales",
        sa.Column("discount_total", sa.Numeric(12, 2), server_default=sa.text("0"), nullable=False),
    )
    op.add_column("sales", sa.Column("idempotency_key", sa.String(100), nullable=True))
    op.create_unique_constraint("uq_sales_idempotency_key", "sales", ["idempotency_key"])
    op.add_column(
        "sale_lines",
        sa.Column(
            "discount_amount",
            sa.Numeric(12, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.drop_constraint(op.f("ck_sales_amounts_non_negative"), "sales", type_="check")
    op.create_check_constraint(
        op.f("ck_sales_amounts_non_negative"),
        "sales",
        "subtotal >= 0 AND discount_total >= 0 AND tax_total >= 0 AND total >= 0",
    )
    op.drop_constraint(op.f("ck_sale_lines_amounts_non_negative"), "sale_lines", type_="check")
    op.create_check_constraint(
        op.f("ck_sale_lines_amounts_non_negative"),
        "sale_lines",
        "unit_price >= 0 AND discount_amount >= 0 AND tax_amount >= 0 AND line_total >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_sale_lines_amounts_non_negative"), "sale_lines", type_="check")
    op.drop_constraint(op.f("ck_sales_amounts_non_negative"), "sales", type_="check")
    op.drop_column("sale_lines", "discount_amount")
    op.drop_constraint(op.f("uq_sales_idempotency_key"), "sales", type_="unique")
    op.drop_column("sales", "idempotency_key")
    op.drop_column("sales", "discount_total")
