"""Add immutable content snapshots to invoices and returns.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-30
"""

import json
from collections.abc import Sequence
from decimal import Decimal

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add nullable content columns
    op.add_column(
        "invoices",
        sa.Column(
            "content",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=True,
        ),
    )
    op.add_column(
        "returns",
        sa.Column(
            "content",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=True,
        ),
    )

    # 2. Backfill existing invoices
    conn = op.get_bind()
    invoice_rows = (
        conn.execute(
            sa.text(
                """
            SELECT i.id, i.invoice_number, i.total, i.issued_at, i.notes,
                   s.id AS sale_id, s.location_id, s.cashier_id, s.subtotal,
                   s.discount_total, s.tax_total, s.total AS sale_total,
                   s.customer_name, s.sold_at,
                   l.name AS location_name, l.address AS location_address,
                   u.username AS cashier_username, u.full_name AS cashier_full_name
            FROM invoices i
            JOIN sales s ON s.id = i.sale_id
            LEFT JOIN locations l ON l.id = s.location_id
            LEFT JOIN users u ON u.id = s.cashier_id
            """
            )
        )
        .mappings()
        .all()
    )

    for inv in invoice_rows:
        lines = (
            conn.execute(
                sa.text(
                    """
                SELECT sl.id, sl.product_id, sl.variant_id, sl.quantity,
                       sl.unit_price, sl.discount_amount, sl.tax_amount, sl.line_total,
                       p.name AS product_name, p.sku AS product_sku,
                       pv.sku AS variant_sku, pv.attributes AS variant_attributes
                FROM sale_lines sl
                LEFT JOIN products p ON p.id = sl.product_id
                LEFT JOIN product_variants pv ON pv.id = sl.variant_id
                WHERE sl.sale_id = :sale_id
                ORDER BY sl.id
                """
                ),
                {"sale_id": inv["sale_id"]},
            )
            .mappings()
            .all()
        )

        payments = (
            conn.execute(
                sa.text(
                    """
                SELECT method, amount, reference
                FROM payments
                WHERE sale_id = :sale_id
                ORDER BY id
                """
                ),
                {"sale_id": inv["sale_id"]},
            )
            .mappings()
            .all()
        )

        snapshot = {
            "version": 1,
            "kind": "invoice",
            "invoice_number": inv["invoice_number"],
            "invoice_label": f"INV-{inv['invoice_number']:04d}",
            "issued_at": inv["issued_at"].isoformat() if inv["issued_at"] else None,
            "store_name": "ESIMS Electronics",
            "store_gstin": None,
            "location_id": inv["location_id"],
            "location_name": inv["location_name"] or f"Location {inv['location_id']}",
            "location_address": inv["location_address"],
            "cashier_id": inv["cashier_id"],
            "cashier_name": inv["cashier_full_name"]
            or inv["cashier_username"]
            or f"User {inv['cashier_id']}",
            "cashier_username": inv["cashier_username"] or f"user_{inv['cashier_id']}",
            "customer_name": inv["customer_name"],
            "gst_rate": "18.00",
            "lines": [
                {
                    "product_id": line["product_id"],
                    "product_name": line["product_name"] or f"Product {line['product_id']}",
                    "sku": line["product_sku"] or f"SKU-{line['product_id']}",
                    "variant_id": line["variant_id"],
                    "variant_sku": line["variant_sku"],
                    "variant_label": (
                        ", ".join(f"{k}: {v}" for k, v in line["variant_attributes"].items())
                        if line.get("variant_attributes")
                        else line["variant_sku"]
                    ),
                    "quantity": line["quantity"],
                    "unit_price": f"{Decimal(str(line['unit_price'])):.2f}",
                    "discount": f"{Decimal(str(line['discount_amount'])):.2f}",
                    "tax": f"{Decimal(str(line['tax_amount'])):.2f}",
                    "line_total": f"{Decimal(str(line['line_total'])):.2f}",
                    "serial_numbers": [],
                    "batch_numbers": [],
                }
                for line in lines
            ],
            "subtotal": f"{Decimal(str(inv['subtotal'])):.2f}",
            "discount_total": f"{Decimal(str(inv['discount_total'])):.2f}",
            "tax_total": f"{Decimal(str(inv['tax_total'])):.2f}",
            "total": f"{Decimal(str(inv['total'])):.2f}",
            "payments": [
                {
                    "method": p["method"],
                    "amount": f"{Decimal(str(p['amount'])):.2f}",
                    "reference": p["reference"],
                }
                for p in payments
            ],
            "notes": inv["notes"],
            "backfilled": True,
        }
        conn.execute(
            sa.text("UPDATE invoices SET content = :content WHERE id = :id"),
            {"content": json.dumps(snapshot), "id": inv["id"]},
        )

    # 3. Backfill existing returns
    return_rows = (
        conn.execute(
            sa.text(
                """
            SELECT r.id, r.sale_id, r.processed_by, r.approved_by, r.reason,
                   r.refund_total, r.created_at,
                   s.sold_at, s.location_id,
                   i.invoice_number,
                   l.name AS location_name, l.address AS location_address,
                   pu.username AS processor_username, pu.full_name AS processor_full_name,
                   au.username AS approver_username, au.full_name AS approver_full_name
            FROM returns r
            JOIN sales s ON s.id = r.sale_id
            LEFT JOIN invoices i ON i.sale_id = s.id
            LEFT JOIN locations l ON l.id = s.location_id
            LEFT JOIN users pu ON pu.id = r.processed_by
            LEFT JOIN users au ON au.id = r.approved_by
            """
            )
        )
        .mappings()
        .all()
    )

    for ret in return_rows:
        rlines = (
            conn.execute(
                sa.text(
                    """
                SELECT rl.id, rl.sale_line_id, rl.quantity, rl.condition,
                       rl.restocked, rl.refund_amount,
                       sl.product_id, sl.variant_id,
                       p.name AS product_name, p.sku AS product_sku,
                       pv.sku AS variant_sku
                FROM return_lines rl
                JOIN sale_lines sl ON sl.id = rl.sale_line_id
                LEFT JOIN products p ON p.id = sl.product_id
                LEFT JOIN product_variants pv ON pv.id = sl.variant_id
                WHERE rl.return_id = :return_id
                ORDER BY rl.id
                """
                ),
                {"return_id": ret["id"]},
            )
            .mappings()
            .all()
        )

        ret_snapshot = {
            "version": 1,
            "kind": "credit_note",
            "credit_note_number": f"CN-{ret['id']:04d}",
            "return_id": ret["id"],
            "sale_id": ret["sale_id"],
            "invoice_number": ret["invoice_number"],
            "invoice_label": f"INV-{ret['invoice_number']:04d}" if ret["invoice_number"] else None,
            "created_at": ret["created_at"].isoformat() if ret["created_at"] else None,
            "sold_at": ret["sold_at"].isoformat() if ret["sold_at"] else None,
            "store_name": "ESIMS Electronics",
            "store_gstin": None,
            "location_id": ret["location_id"],
            "location_name": ret["location_name"] or f"Location {ret['location_id']}",
            "location_address": ret["location_address"],
            "processor_id": ret["processed_by"],
            "processor_name": ret["processor_full_name"]
            or ret["processor_username"]
            or f"User {ret['processed_by']}",
            "processor_username": ret["processor_username"] or f"user_{ret['processed_by']}",
            "approver_id": ret["approved_by"],
            "approver_name": (
                (ret["approver_full_name"] or ret["approver_username"])
                if ret["approved_by"]
                else None
            ),
            "approver_username": ret["approver_username"],
            "reason": ret["reason"] or "",
            "refund_total": f"{Decimal(str(ret['refund_total'])):.2f}",
            "lines": [
                {
                    "id": rl["id"],
                    "sale_line_id": rl["sale_line_id"],
                    "product_id": rl["product_id"],
                    "product_name": rl["product_name"] or f"Product {rl['product_id']}",
                    "sku": rl["product_sku"] or f"SKU-{rl['product_id']}",
                    "variant_id": rl["variant_id"],
                    "variant_sku": rl["variant_sku"],
                    "quantity": rl["quantity"],
                    "condition": rl["condition"],
                    "restocked": bool(rl["restocked"]),
                    "refund_amount": f"{Decimal(str(rl['refund_amount'])):.2f}",
                    "serial_numbers": [],
                }
                for rl in rlines
            ],
            "backfilled": True,
        }
        conn.execute(
            sa.text("UPDATE returns SET content = :content WHERE id = :id"),
            {"content": json.dumps(ret_snapshot), "id": ret["id"]},
        )

    # 4. Make content NOT NULL with server_default
    op.alter_column(
        "invoices",
        "content",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        server_default=sa.text("'{}'::jsonb"),
        nullable=False,
    )
    op.alter_column(
        "returns",
        "content",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        server_default=sa.text("'{}'::jsonb"),
        nullable=False,
    )

    # 5. Immutability triggers
    # Invoices: reject any UPDATE
    op.execute(
        """
        CREATE TRIGGER invoices_no_update
            BEFORE UPDATE ON invoices
            FOR EACH ROW EXECUTE FUNCTION reject_modification();
        """
    )

    # Returns: reject any UPDATE on content
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_return_content_modification()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.content IS NOT NULL AND OLD.content::text <> '{}'
               AND NEW.content IS DISTINCT FROM OLD.content THEN
                RAISE EXCEPTION 'returns.content is immutable; UPDATE is not allowed'
                    USING ERRCODE = 'insufficient_privilege';
            END IF;
            RETURN NEW;
        END;
        $$;

        CREATE TRIGGER returns_content_immutable
            BEFORE UPDATE OF content ON returns
            FOR EACH ROW EXECUTE FUNCTION reject_return_content_modification();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS returns_content_immutable ON returns")
    op.execute("DROP FUNCTION IF EXISTS reject_return_content_modification()")
    op.execute("DROP TRIGGER IF EXISTS invoices_no_update ON invoices")
    op.drop_column("returns", "content")
    op.drop_column("invoices", "content")
