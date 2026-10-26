"""Add product tracking modes and aggregate batch traceability."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_serial_numbers_status"), "serial_numbers", type_="check")
    op.create_check_constraint(
        op.f("ck_serial_numbers_status"),
        "serial_numbers",
        "status IN ('in_stock', 'sold', 'returned', 'damaged', 'removed')",
    )
    op.add_column(
        "products",
        sa.Column(
            "tracking_mode",
            sa.String(length=20),
            server_default=sa.text("'untracked'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_products_tracking_mode"),
        "products",
        "tracking_mode IN ('untracked', 'batch', 'serial')",
    )
    op.create_table(
        "batch_stock",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column("quantity_received", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("quantity_on_hand", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.CheckConstraint(
            "quantity_received >= 0",
            name=op.f("ck_batch_stock_quantity_received_non_negative"),
        ),
        sa.CheckConstraint(
            "quantity_on_hand >= 0", name=op.f("ck_batch_stock_quantity_on_hand_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["batches.id"],
            ondelete="RESTRICT",
            name=op.f("fk_batch_stock_batch_id_batches"),
        ),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["locations.id"],
            ondelete="RESTRICT",
            name=op.f("fk_batch_stock_location_id_locations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_batch_stock")),
        sa.UniqueConstraint(
            "batch_id", "location_id", name=op.f("uq_batch_stock_batch_id_location_id")
        ),
    )
    op.create_index("ix_batch_stock_location_id", "batch_stock", ["location_id"])
    op.create_table(
        "batch_receipts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column("reference_type", sa.String(length=50), nullable=False),
        sa.Column("reference_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_batch_receipts_quantity_positive")),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["batches.id"],
            ondelete="RESTRICT",
            name=op.f("fk_batch_receipts_batch_id_batches"),
        ),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["locations.id"],
            ondelete="RESTRICT",
            name=op.f("fk_batch_receipts_location_id_locations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_batch_receipts")),
        sa.UniqueConstraint(
            "batch_id",
            "location_id",
            "reference_type",
            "reference_id",
            name=op.f("uq_batch_receipts_batch_id_location_id_reference_type_reference_id"),
        ),
    )
    op.create_index("ix_batch_receipts_batch_id", "batch_receipts", ["batch_id"])
    op.create_table(
        "sale_line_batches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sale_line_id", sa.Integer(), nullable=False),
        sa.Column("batch_stock_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_sale_line_batches_quantity_positive")),
        sa.ForeignKeyConstraint(
            ["sale_line_id"],
            ["sale_lines.id"],
            ondelete="RESTRICT",
            name=op.f("fk_sale_line_batches_sale_line_id_sale_lines"),
        ),
        sa.ForeignKeyConstraint(
            ["batch_stock_id"],
            ["batch_stock.id"],
            ondelete="RESTRICT",
            name=op.f("fk_sale_line_batches_batch_stock_id_batch_stock"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sale_line_batches")),
    )
    op.create_index("ix_sale_line_batches_sale_line_id", "sale_line_batches", ["sale_line_id"])
    op.create_table(
        "return_line_serials",
        sa.Column("return_line_id", sa.Integer(), nullable=False),
        sa.Column("serial_number_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["return_line_id"],
            ["return_lines.id"],
            ondelete="RESTRICT",
            name=op.f("fk_return_line_serials_return_line_id_return_lines"),
        ),
        sa.ForeignKeyConstraint(
            ["serial_number_id"],
            ["serial_numbers.id"],
            ondelete="RESTRICT",
            name=op.f("fk_return_line_serials_serial_number_id_serial_numbers"),
        ),
        sa.PrimaryKeyConstraint(
            "return_line_id", "serial_number_id", name=op.f("pk_return_line_serials")
        ),
    )
    op.create_table(
        "return_line_batches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("return_line_id", sa.Integer(), nullable=False),
        sa.Column("sale_line_batch_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_return_line_batches_quantity_positive")),
        sa.ForeignKeyConstraint(
            ["return_line_id"],
            ["return_lines.id"],
            ondelete="RESTRICT",
            name=op.f("fk_return_line_batches_return_line_id_return_lines"),
        ),
        sa.ForeignKeyConstraint(
            ["sale_line_batch_id"],
            ["sale_line_batches.id"],
            ondelete="RESTRICT",
            name=op.f("fk_return_line_batches_sale_line_batch_id_sale_line_batches"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_return_line_batches")),
    )
    op.create_index(
        "ix_return_line_batches_return_line_id", "return_line_batches", ["return_line_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_return_line_batches_return_line_id", table_name="return_line_batches")
    op.drop_table("return_line_batches")
    op.drop_table("return_line_serials")
    op.drop_index("ix_batch_receipts_batch_id", table_name="batch_receipts")
    op.drop_table("batch_receipts")
    op.drop_index("ix_sale_line_batches_sale_line_id", table_name="sale_line_batches")
    op.drop_table("sale_line_batches")
    op.drop_index("ix_batch_stock_location_id", table_name="batch_stock")
    op.drop_table("batch_stock")
    op.drop_constraint(op.f("ck_products_tracking_mode"), "products", type_="check")
    op.drop_column("products", "tracking_mode")
    op.drop_constraint(op.f("ck_serial_numbers_status"), "serial_numbers", type_="check")
    op.create_check_constraint(
        op.f("ck_serial_numbers_status"),
        "serial_numbers",
        "status IN ('in_stock', 'sold', 'returned', 'damaged')",
    )
