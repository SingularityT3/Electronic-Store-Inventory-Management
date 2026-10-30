"""Protect sales records inside the minimum retention window.

Revision ID: 0013
Revises: 0012
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "sales",
    "sale_lines",
    "sale_line_serials",
    "sale_line_batches",
    "payments",
    "returns",
    "return_lines",
    "return_line_serials",
    "return_line_batches",
    "invoices",
)


def upgrade() -> None:
    # Resolve every child to its transaction's immutable clock date.
    queries = {
        "sales": ("SELECT sold_at FROM sales WHERE id=$1", "id"),
        "sale_lines": (
            "SELECT s.sold_at FROM sales s JOIN sale_lines x ON x.sale_id=s.id WHERE x.id=$1",
            "id",
        ),
        "sale_line_serials": (
            "SELECT s.sold_at FROM sales s JOIN sale_lines l ON l.sale_id=s.id WHERE l.id=$1",
            "sale_line_id",
        ),
        "sale_line_batches": (
            "SELECT s.sold_at FROM sales s JOIN sale_lines l ON l.sale_id=s.id WHERE l.id=$1",
            "sale_line_id",
        ),
        "payments": (
            "SELECT s.sold_at FROM sales s JOIN payments x ON x.sale_id=s.id WHERE x.id=$1",
            "id",
        ),
        "returns": ("SELECT created_at FROM returns WHERE id=$1", "id"),
        "return_lines": (
            "SELECT r.created_at FROM returns r JOIN return_lines x ON x.return_id=r.id WHERE x.id=$1",  # noqa: E501
            "id",
        ),
        "return_line_serials": (
            "SELECT r.created_at FROM returns r JOIN return_lines x ON x.return_id=r.id WHERE x.id=$1",  # noqa: E501
            "return_line_id",
        ),
        "return_line_batches": (
            "SELECT r.created_at FROM returns r JOIN return_lines x ON x.return_id=r.id WHERE x.id=$1",  # noqa: E501
            "return_line_id",
        ),
        "invoices": ("SELECT issued_at FROM invoices WHERE id=$1", "id"),
    }
    op.execute("""
        CREATE FUNCTION reject_retained_delete() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE transaction_date timestamptz;
        BEGIN
            EXECUTE TG_ARGV[0] INTO transaction_date
                USING (to_jsonb(OLD)->>TG_ARGV[1])::bigint;
            IF transaction_date + interval '8 years' > now() THEN
                RAISE EXCEPTION 'Records inside the retention period cannot be deleted'
                    USING ERRCODE = 'restrict_violation';
            END IF;
            RETURN OLD;
        END $$;
        CREATE FUNCTION reject_retained_truncate() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Records inside the retention period cannot be truncated'
                USING ERRCODE = 'restrict_violation';
        END $$;
    """)
    for table in TABLES:
        query, key = queries[table]
        op.execute(
            f"CREATE TRIGGER {table}_retention_delete BEFORE DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION reject_retained_delete('{query}', '{key}')"  # noqa: E501
        )
        op.execute(
            f"CREATE TRIGGER {table}_retention_truncate BEFORE TRUNCATE ON {table} FOR EACH STATEMENT EXECUTE FUNCTION reject_retained_truncate()"  # noqa: E501
        )
    for table, columns in (
        ("sales", "sold_at"),
        ("returns", "created_at"),
        ("invoices", "issued_at, invoice_number, total, content"),
    ):
        op.execute(f"""
            CREATE TRIGGER {table}_retention_clock_immutable
            BEFORE UPDATE OF {columns} ON {table}
            FOR EACH ROW EXECUTE FUNCTION reject_modification()
        """)


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_retention_delete ON {table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_retention_truncate ON {table}")
    for table in ("sales", "returns", "invoices"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_retention_clock_immutable ON {table}")
    op.execute("DROP FUNCTION IF EXISTS reject_retained_delete()")
    op.execute("DROP FUNCTION IF EXISTS reject_retained_truncate()")
