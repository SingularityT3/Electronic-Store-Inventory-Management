"""Add current per-location stock alert state."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stock_alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("variant_id", sa.Integer(), nullable=True),
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column("product_name", sa.String(length=200), nullable=False),
        sa.Column("sku", sa.String(length=100), nullable=False),
        sa.Column("variant_sku", sa.String(length=100), nullable=True),
        sa.Column("location_name", sa.String(length=100), nullable=False),
        sa.Column("alert_type", sa.String(length=30), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("threshold", sa.Integer(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "alert_type IS NULL OR alert_type IN ('low_stock', 'out_of_stock')",
            name=op.f("ck_stock_alerts_alert_type"),
        ),
        sa.CheckConstraint(
            "alert_type IS NULL OR quantity <= threshold",
            name=op.f("ck_stock_alerts_below_threshold"),
        ),
        sa.CheckConstraint(
            "alert_type <> 'out_of_stock' OR quantity = 0",
            name=op.f("ck_stock_alerts_out_of_stock_quantity"),
        ),
        sa.CheckConstraint(
            "quantity >= 0",
            name=op.f("ck_stock_alerts_quantity_non_negative"),
        ),
        sa.CheckConstraint(
            "threshold >= 0",
            name=op.f("ck_stock_alerts_threshold_non_negative"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_alerts")),
        sa.UniqueConstraint(
            "product_id",
            "variant_id",
            "location_id",
            name=op.f("uq_stock_alerts_product_id_variant_id_location_id"),
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index(
        "ix_stock_alerts_location_active",
        "stock_alerts",
        ["location_id", "alert_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_stock_alerts_location_active", table_name="stock_alerts")
    op.drop_table("stock_alerts")
