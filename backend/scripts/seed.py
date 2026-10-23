"""Load sample data for manual testing: locations, categories, products, stock,
suppliers, and one user per role.

Run after migrating: `python -m scripts.seed`. Safe to run repeatedly: rows are looked up by
their natural key and only missing ones are added. User passwords come from
SEED_USER_PASSWORD; nothing is hard-coded (SEC-DAT-6).
"""

import sys
from decimal import Decimal
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import Base, get_engine
from app.modules.auth._internal.models import User
from app.modules.auth._internal.passwords import hash_password
from app.modules.product._internal.models import (
    Category,
    CategoryAttribute,
    Product,
    ProductVariant,
)
from app.modules.purchasing._internal.models import Supplier, SupplierProduct
from app.modules.stock._internal.models import ItemCost, Location, StockLevel
from migrations import models  # noqa: F401  (registers every table, so all FKs resolve)

LOCATIONS = [
    ("Main Street Store", "store", "12 Main Street, Bengaluru"),
    ("Mall Road Store", "store", "Level 2, City Mall, Bengaluru"),
    ("Central Warehouse", "warehouse", "Plot 7, Industrial Area, Bengaluru"),
]

# (name, parent name)
CATEGORIES = [
    ("Electronics", None),
    ("Mobile Phones", "Electronics"),
    ("Smartphones", "Mobile Phones"),
    ("Phones", None),
    ("Feature Phones", "Phones"),
    ("Laptops", None),
    ("Audio", None),
    ("Headphones", "Audio"),
    ("Speakers", "Audio"),
    ("Accessories", None),
    ("Chargers", "Accessories"),
    ("Cables", "Accessories"),
]

# (sku, name, category, brand, price, cost, variants as (sku, attributes, price))
PRODUCTS: list[tuple[str, str, str, str, str, str, list[tuple[str, dict[str, str], str]]]] = [
    (
        "PH-GAL-S24",
        "Galaxy S24",
        "Smartphones",
        "Samsung",
        "74999.00",
        "61000.00",
        [
            ("PH-GAL-S24-BLK-128", {"color": "Black", "storage": "128GB"}, "74999.00"),
            ("PH-GAL-S24-BLK-256", {"color": "Black", "storage": "256GB"}, "79999.00"),
            ("PH-GAL-S24-VIO-256", {"color": "Violet", "storage": "256GB"}, "79999.00"),
        ],
    ),
    ("PH-RED-13C", "Redmi 13C", "Smartphones", "Xiaomi", "8999.00", "7100.00", []),
    ("PH-NOK-105", "Nokia 105", "Feature Phones", "Nokia", "1299.00", "950.00", []),
    (
        "LP-IDP-5",
        "IdeaPad Slim 5",
        "Laptops",
        "Lenovo",
        "62990.00",
        "52000.00",
        [
            ("LP-IDP-5-16-512", {"ram": "16GB", "storage": "512GB"}, "62990.00"),
            ("LP-IDP-5-16-1T", {"ram": "16GB", "storage": "1TB"}, "69990.00"),
        ],
    ),
    ("LP-MBA-M3", "MacBook Air M3", "Laptops", "Apple", "114900.00", "98000.00", []),
    ("AU-SNY-XM5", "WH-1000XM5", "Headphones", "Sony", "29990.00", "23500.00", []),
    ("AU-BOT-131", "Airdopes 131", "Headphones", "boAt", "1299.00", "800.00", []),
    ("AU-JBL-FL6", "Flip 6", "Speakers", "JBL", "11999.00", "9200.00", []),
    ("AC-ANK-65W", "65W USB-C Charger", "Chargers", "Anker", "3499.00", "2400.00", []),
    ("AC-SAM-25W", "25W Travel Adapter", "Chargers", "Samsung", "1499.00", "1000.00", []),
    ("AC-BLK-C2C", "USB-C to USB-C Cable 1m", "Cables", "Belkin", "999.00", "550.00", []),
    ("AC-ANK-LTG", "Lightning Cable 1.8m", "Cables", "Anker", "1299.00", "700.00", []),
]

# (name, contact fields, product SKUs in the supplier's catalog)
SUPPLIERS = [
    (
        "Metro Electronics Distributors",
        {
            "contact_name": "R. Iyer",
            "email": "orders@metro-distributors.example",
            "phone": "+91 80 4000 1000",
            "address": "Peenya Industrial Area, Bengaluru",
        },
        ["PH-GAL-S24", "PH-RED-13C", "PH-NOK-105", "AC-SAM-25W"],
    ),
    (
        "Southern Tech Supplies",
        {
            "contact_name": "A. Menon",
            "email": "sales@southern-tech.example",
            "phone": "+91 44 4000 2000",
            "address": "Guindy, Chennai",
        },
        ["LP-IDP-5", "LP-MBA-M3", "AU-SNY-XM5", "AU-JBL-FL6", "AC-ANK-65W", "AC-BLK-C2C"],
    ),
]

# (username, full name, role, location name or None)
USERS = [
    ("admin", "System Administrator", "admin", None),
    ("manager", "Store Manager", "manager", None),
    ("staff", "Stock Staff", "staff", "Central Warehouse"),
    ("cashier", "Counter Cashier", "cashier", "Main Street Store"),
]


def _get_or_add(session: Session, model: type[Base], key: dict[str, Any], **values: Any) -> Any:
    """Return the row matching `key`, inserting it with `values` if it does not exist."""
    query = select(model)
    for column, value in key.items():
        attr = getattr(model, column)
        query = query.where(attr.is_(None) if value is None else attr == value)
    row = session.scalars(query).one_or_none()
    if row is None:
        row = model(**key, **values)
        session.add(row)
        session.flush()
    return row


def seed(engine: Engine, password: str) -> None:
    with Session(engine) as session, session.begin():
        locations = {
            name: _get_or_add(session, Location, {"name": name}, type=kind, address=address)
            for name, kind, address in LOCATIONS
        }

        categories: dict[str, Category] = {}
        for name, parent in CATEGORIES:
            parent_id = categories[parent].id if parent else None
            categories[name] = _get_or_add(
                session, Category, {"name": name, "parent_id": parent_id}
            )
        _get_or_add(
            session,
            CategoryAttribute,
            {"category_id": categories["Mobile Phones"].id, "name": "Color"},
            position=0,
            allowed_values=["Black", "White", "Violet"],
        )
        _get_or_add(
            session,
            CategoryAttribute,
            {"category_id": categories["Mobile Phones"].id, "name": "Storage"},
            position=1,
            allowed_values=["64GB", "128GB", "256GB", "512GB"],
        )

        # Stocked items per product SKU: [(product_id, variant_id, price)]
        items: dict[str, list[tuple[int, int | None, Decimal]]] = {}
        for sku, name, category, brand, price, cost, variants in PRODUCTS:
            product = _get_or_add(
                session,
                Product,
                {"sku": sku},
                name=name,
                category_id=categories[category].id,
                brand=brand,
                price=Decimal(price),
                description=f"{brand} {name}",
            )
            items[sku] = []
            for variant_sku, attributes, variant_price in variants:
                variant = _get_or_add(
                    session,
                    ProductVariant,
                    {"sku": variant_sku},
                    product_id=product.id,
                    attributes=attributes,
                    price=Decimal(variant_price),
                )
                items[sku].append((product.id, variant.id, Decimal(cost)))
            if not variants:
                items[sku].append((product.id, None, Decimal(cost)))

        for index, item_list in enumerate(items.values()):
            for product_id, variant_id, cost in item_list:
                item = {"product_id": product_id, "variant_id": variant_id}
                _get_or_add(session, ItemCost, item, average_cost=cost)
                for loc_index, location in enumerate(locations.values()):
                    # Varied quantities; every fourth item is low at the first store.
                    quantity = 3 if index % 4 == 0 and loc_index == 0 else 10 + 5 * loc_index
                    _get_or_add(
                        session,
                        StockLevel,
                        {**item, "location_id": location.id},
                        quantity=quantity,
                        reorder_threshold=5,
                    )

        for name, contact, skus in SUPPLIERS:
            supplier = _get_or_add(session, Supplier, {"name": name}, **contact)
            for sku in skus:
                for product_id, variant_id, cost in items[sku]:
                    _get_or_add(
                        session,
                        SupplierProduct,
                        {
                            "supplier_id": supplier.id,
                            "product_id": product_id,
                            "variant_id": variant_id,
                        },
                        supplier_price=cost,
                    )

        password_hash = hash_password(password)
        for username, full_name, role, location in USERS:
            _get_or_add(
                session,
                User,
                {"username": username},
                full_name=full_name,
                role=role,
                location_id=locations[location].id if location else None,
                password_hash=password_hash,
            )


def main() -> None:
    password = get_settings().seed_user_password
    if not password:
        sys.exit("Set SEED_USER_PASSWORD to the password for the seeded users.")
    seed(get_engine(), password)
    print("Seed data loaded.")


if __name__ == "__main__":
    main()
