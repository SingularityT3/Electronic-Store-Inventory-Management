"""Business rules enforced by the database itself, not only by application code."""

from typing import Any

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import DBAPIError


def insert(conn: Connection, sql: str, **params: Any) -> int:
    return conn.execute(text(sql + " RETURNING id"), params).scalar_one()


def assert_rejected(conn: Connection, sql: str, constraint: str | None = None, **params: Any):
    """Run `sql` in a savepoint and check the database rejects it."""
    with pytest.raises(DBAPIError) as info, conn.begin_nested():
        conn.execute(text(sql), params)
    if constraint is not None:
        assert info.value.orig.diag.constraint_name == constraint
    return info.value


@pytest.fixture
def ids(conn):
    """A minimal set of rows to reference: category, product, variant, location, user."""
    category = insert(conn, "INSERT INTO categories (name) VALUES ('Test')")
    product = insert(
        conn,
        "INSERT INTO products (sku, name, category_id, brand, price) "
        "VALUES ('T-PROD', 'Test phone', :c, 'Acme', 100)",
        c=category,
    )
    variant = insert(
        conn,
        "INSERT INTO product_variants (product_id, sku, attributes) "
        """VALUES (:p, 'T-VAR', '{"color": "Black", "storage": "128GB"}')""",
        p=product,
    )
    location = insert(conn, "INSERT INTO locations (name, type) VALUES ('Test store', 'store')")
    user = insert(
        conn,
        "INSERT INTO users (username, full_name, password_hash, role) "
        "VALUES ('t-manager', 'Test', 'x', 'manager')",
    )
    return {
        "category": category,
        "product": product,
        "variant": variant,
        "location": location,
        "user": user,
    }


PRODUCT_SQL = (
    "INSERT INTO products (sku, name, category_id, brand, price) "
    "VALUES (:sku, 'Other', :c, 'Acme', 1)"
)
VARIANT_SQL = "INSERT INTO product_variants (product_id, sku, attributes) VALUES (:p, :sku, :attrs)"


def test_duplicate_product_sku_rejected(conn, ids):
    assert_rejected(conn, PRODUCT_SQL, "uq_products_sku", sku="T-PROD", c=ids["category"])


def test_retention_blocks_truncate_for_all_sales_tables(conn):
    tables = (
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
    for table in tables:
        assert_rejected(conn, f"TRUNCATE TABLE {table} CASCADE")


def test_duplicate_variant_sku_rejected(conn, ids):
    assert_rejected(
        conn,
        VARIANT_SQL,
        "uq_product_variants_sku",
        p=ids["product"],
        sku="T-VAR",
        attrs='{"color": "Red"}',
    )


def test_sku_shared_between_products_and_variants(conn, ids):
    error = assert_rejected(
        conn, VARIANT_SQL, p=ids["product"], sku="T-PROD", attrs='{"color": "Red"}'
    )
    assert error.orig.sqlstate == "23505"  # unique_violation
    error = assert_rejected(conn, PRODUCT_SQL, sku="T-VAR", c=ids["category"])
    assert error.orig.sqlstate == "23505"


def test_duplicate_variant_combination_rejected(conn, ids):
    # Same attributes in a different key order is the same combination.
    assert_rejected(
        conn,
        VARIANT_SQL,
        "uq_product_variants_product_id_attributes",
        p=ids["product"],
        sku="T-VAR-2",
        attrs='{"storage": "128GB", "color": "Black"}',
    )


def test_empty_variant_attributes_rejected(conn, ids):
    assert_rejected(
        conn,
        VARIANT_SQL,
        "ck_product_variants_attributes_non_empty_object",
        p=ids["product"],
        sku="T-VAR-3",
        attrs="{}",
    )


def test_negative_stock_rejected(conn, ids):
    stock = insert(
        conn,
        "INSERT INTO stock_levels (product_id, variant_id, location_id, quantity) "
        "VALUES (:p, :v, :l, 1)",
        p=ids["product"],
        v=ids["variant"],
        l=ids["location"],
    )
    assert_rejected(
        conn,
        "UPDATE stock_levels SET quantity = quantity - 2 WHERE id = :id",
        "ck_stock_levels_quantity_non_negative",
        id=stock,
    )


def test_one_stock_row_per_item_and_location(conn, ids):
    sql = "INSERT INTO stock_levels (product_id, location_id) VALUES (:p, :l)"
    conn.execute(text(sql), {"p": ids["product"], "l": ids["location"]})
    # variant_id is NULL in both rows; NULLS NOT DISTINCT still treats them as equal.
    assert_rejected(
        conn,
        sql,
        "uq_stock_levels_product_id_variant_id_location_id",
        p=ids["product"],
        l=ids["location"],
    )


def test_adjustment_requires_reason(conn, ids):
    sql = (
        "INSERT INTO stock_movements "
        "(product_id, location_id, quantity_change, movement_type, reason_code, reason) "
        "VALUES (:p, :l, -1, 'adjustment', :code, :reason)"
    )
    item = {"p": ids["product"], "l": ids["location"]}
    for code, reason in [(None, None), ("damage", None), ("damage", "  ")]:
        assert_rejected(
            conn,
            sql,
            "ck_stock_movements_adjustment_requires_reason",
            code=code,
            reason=reason,
            **item,
        )
    conn.execute(text(sql), {"code": "damage", "reason": "Dropped in store", **item})


def test_invoice_numbers_unique_and_sequential(conn, ids):
    sales = [
        insert(
            conn,
            "INSERT INTO sales (location_id, cashier_id, subtotal, total) VALUES (:l, :u, 1, 1)",
            l=ids["location"],
            u=ids["user"],
        )
        for _ in range(3)
    ]
    numbers = [
        conn.execute(
            text("INSERT INTO invoices (sale_id, total) VALUES (:s, 1) RETURNING invoice_number"),
            {"s": sale},
        ).scalar_one()
        for sale in sales[:2]
    ]
    assert numbers[1] == numbers[0] + 1
    assert_rejected(
        conn,
        "INSERT INTO invoices (sale_id, total, invoice_number) VALUES (:s, 1, :n)",
        "uq_invoices_invoice_number",
        s=sales[2],
        n=numbers[0],
    )
    assert_rejected(
        conn,
        "INSERT INTO invoices (sale_id, total) VALUES (:s, 1)",
        "uq_invoices_sale_id",
        s=sales[0],
    )


@pytest.mark.parametrize(
    "sql",
    ["UPDATE audit_log SET action = 'tampered'", "DELETE FROM audit_log"],
)
def test_audit_log_is_append_only(conn, sql):
    conn.execute(text("INSERT INTO audit_log (module, action) VALUES ('stock', 'adjust')"))
    error = assert_rejected(conn, sql)
    assert "append-only" in str(error.orig)


@pytest.mark.parametrize(
    "sql",
    ["UPDATE supplier_price_history SET unit_price = 0", "DELETE FROM supplier_price_history"],
)
def test_supplier_price_history_is_append_only(conn, ids, sql):
    supplier = insert(conn, "INSERT INTO suppliers (name) VALUES ('Test supplier')")
    conn.execute(
        text(
            "INSERT INTO supplier_price_history (supplier_id, product_id, unit_price) "
            "VALUES (:s, :p, 50)"
        ),
        {"s": supplier, "p": ids["product"]},
    )
    error = assert_rejected(conn, sql)
    assert "append-only" in str(error.orig)


@pytest.mark.parametrize("role", ["staff", "cashier"])
def test_staff_and_cashier_need_a_location(conn, role):
    assert_rejected(
        conn,
        "INSERT INTO users (username, full_name, password_hash, role) "
        "VALUES ('t-user', 'Test', 'x', :role)",
        "ck_users_location_required_for_role",
        role=role,
    )


def test_usernames_unique_ignoring_case(conn, ids):
    assert_rejected(
        conn,
        "INSERT INTO users (username, full_name, password_hash, role) "
        "VALUES ('T-Manager', 'Test', 'x', 'admin')",
        "uq_users_username_lower",
    )


def test_po_line_cannot_receive_more_than_ordered(conn, ids):
    supplier = insert(conn, "INSERT INTO suppliers (name) VALUES ('PO supplier')")
    po = insert(
        conn,
        "INSERT INTO purchase_orders (po_number, supplier_id, location_id, created_by) "
        "VALUES ('PO-T-1', :s, :l, :u)",
        s=supplier,
        l=ids["location"],
        u=ids["user"],
    )
    line = insert(
        conn,
        "INSERT INTO purchase_order_lines (purchase_order_id, product_id, quantity_ordered, "
        "unit_price) VALUES (:po, :p, 5, 10)",
        po=po,
        p=ids["product"],
    )
    assert_rejected(
        conn,
        "UPDATE purchase_order_lines SET quantity_received = 6 WHERE id = :id",
        "ck_purchase_order_lines_quantity_received_within_ordered",
        id=line,
    )


def test_damaged_return_cannot_be_restocked(conn, ids):
    sale = insert(
        conn,
        "INSERT INTO sales (location_id, cashier_id, subtotal, total) VALUES (:l, :u, 1, 1)",
        l=ids["location"],
        u=ids["user"],
    )
    sale_line = insert(
        conn,
        "INSERT INTO sale_lines (sale_id, product_id, quantity, unit_price, line_total) "
        "VALUES (:s, :p, 1, 1, 1)",
        s=sale,
        p=ids["product"],
    )
    ret = insert(
        conn, "INSERT INTO returns (sale_id, processed_by) VALUES (:s, :u)", s=sale, u=ids["user"]
    )
    assert_rejected(
        conn,
        "INSERT INTO return_lines (return_id, sale_line_id, quantity, condition, restocked) "
        "VALUES (:r, :sl, 1, 'damaged', true)",
        "ck_return_lines_damaged_not_restocked",
        r=ret,
        sl=sale_line,
    )


def test_category_cannot_be_its_own_parent(conn, ids):
    assert_rejected(
        conn,
        "UPDATE categories SET parent_id = id WHERE id = :id",
        "ck_categories_not_own_parent",
        id=ids["category"],
    )
