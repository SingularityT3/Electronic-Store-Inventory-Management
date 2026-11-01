"""add_notification_columns

Revision ID: 81510a17a0fa
Revises: 0013
Create Date: 2026-10-31 04:21:35.450282
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "81510a17a0fa"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add dismissed_at and resolved_at columns to notifications table
    op.add_column(
        "notifications", sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "notifications", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True)
    )

    # Partial unique index: one active notification per recipient per alert per type
    op.create_index(
        "ix_notifications_one_active_per_recipient_alert",
        "notifications",
        ["recipient_user_id", "type", "reference_type", "reference_id"],
        unique=True,
        postgresql_where=sa.text(
            "resolved_at IS NULL AND dismissed_at IS NULL " "AND reference_type = 'stock_alert'"
        ),
    )

    # Index for unread count and active list (recipient, dismissed/resolved state, created_at)
    op.create_index(
        "ix_notifications_recipient_active_created",
        "notifications",
        ["recipient_user_id", "dismissed_at", "resolved_at", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_recipient_active_created", table_name="notifications")
    op.drop_index("ix_notifications_one_active_per_recipient_alert", table_name="notifications")
    op.drop_column("notifications", "resolved_at")
    op.drop_column("notifications", "dismissed_at")
