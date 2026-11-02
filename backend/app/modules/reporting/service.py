"""Public service interface of the `reporting` module."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from sqlalchemy.orm import Session

from app.modules.product import product_catalog_items, product_stock_items
from app.modules.purchasing import (
    SupplierReportOrder,
    SupplierReportPrice,
    supplier_catalog_costs,
    supplier_report_sources,
)
from app.modules.reporting._internal.export import ReportTable
from app.modules.sales import SalesTotalsByProduct, sales_totals_by_product
from app.modules.stock import StockPosition, stock_positions


@dataclass(frozen=True)
class ValuationRow:
    position: StockPosition
    unit_cost: Decimal
    value: Decimal
    cost_not_set: bool


@dataclass(frozen=True)
class SalesTrendRow:
    rank: int
    product_id: int
    sku: str
    name: str
    brand: str
    category_name: str
    units_sold: int
    units_returned: int
    net_units: int
    gross_amount: Decimal
    refunded_amount: Decimal
    net_amount: Decimal
    current_stock: int
    inactive: bool


@dataclass(frozen=True)
class SalesTrendReport:
    rows: list[SalesTrendRow]
    units_sold: int
    units_returned: int
    net_units: int
    gross_amount: Decimal
    refunded_amount: Decimal
    net_amount: Decimal
    products_with_sales: int
    products_with_zero_sales: int


@dataclass(frozen=True)
class SupplierPricePoint:
    recorded_at: datetime
    unit_price: Decimal


@dataclass(frozen=True)
class SupplierProductPriceTrend:
    product_id: int
    product_name: str
    sku: str
    variant_id: int | None
    price_points: list[SupplierPricePoint]
    first_price: Decimal
    latest_price: Decimal
    variance: Decimal | None
    variance_percent: Decimal | None


@dataclass(frozen=True)
class SupplierPerformance:
    supplier_id: int
    supplier_name: str
    purchase_order_count: int
    total_order_value: Decimal
    on_time_delivery_rate: Decimal | None
    on_time_delivery_count: int
    eligible_delivery_count: int
    fulfilment_accuracy: Decimal | None
    quantity_ordered: int
    quantity_accepted: int
    price_trends: list[SupplierProductPriceTrend]


class ReportingService(Protocol):
    """Operations the `reporting` module offers to other modules.

    Methods are added as features land; callers depend on this interface,
    never on `_internal`.
    """


def supplier_performance_rows(
    db: Session,
    *,
    start: datetime,
    end: datetime,
    supplier_ids: list[int] | None = None,
) -> list[SupplierPerformance]:
    """Aggregate one PO cohort per supplier and selected-period price history."""
    suppliers, orders, prices = supplier_report_sources(
        db, start=start, end=end, supplier_ids=supplier_ids
    )
    orders_by_supplier: dict[int, list[SupplierReportOrder]] = {
        supplier.id: [] for supplier in suppliers
    }
    for order in orders:
        orders_by_supplier[order.supplier_id].append(order)

    prices_by_supplier_product: dict[tuple[int, int, int | None], list[SupplierReportPrice]] = {}
    product_ids = {price.product_id for price in prices}
    for price in prices:
        key = (price.supplier_id, price.product_id, price.variant_id)
        prices_by_supplier_product.setdefault(key, []).append(price)
    item_names = {
        (item.product_id, item.variant_id): (item.product_name, item.variant_sku or item.sku)
        for item in product_stock_items(db, product_ids)
    }

    reports = []
    for supplier in suppliers:
        supplier_orders = orders_by_supplier[supplier.id]
        eligible_deliveries = 0
        on_time_deliveries = 0
        for order in supplier_orders:
            if order.expected_delivery_date is None or order.first_receipt_at is None:
                continue
            actual_date = order.first_receipt_at
            if actual_date.tzinfo is not None:
                actual_date = actual_date.astimezone(UTC)
            eligible_deliveries += 1
            on_time_deliveries += actual_date.date() <= order.expected_delivery_date

        quantity_ordered = sum(order.quantity_ordered for order in supplier_orders)
        quantity_accepted = sum(order.quantity_accepted for order in supplier_orders)
        on_time_rate = (
            (Decimal(on_time_deliveries) * 100 / eligible_deliveries).quantize(Decimal("0.01"))
            if eligible_deliveries
            else None
        )
        fulfilment_accuracy = (
            (Decimal(quantity_accepted) * 100 / quantity_ordered).quantize(Decimal("0.01"))
            if quantity_ordered
            else None
        )

        trends = []
        supplier_keys = sorted(
            (key for key in prices_by_supplier_product if key[0] == supplier.id),
            key=lambda key: (
                item_names.get((key[1], key[2]), (f"Product {key[1]}", ""))[0].casefold(),
                key[2] or 0,
            ),
        )
        for key in supplier_keys:
            entries = prices_by_supplier_product[key]
            first_price = entries[0].unit_price
            latest_price = entries[-1].unit_price
            variance = latest_price - first_price if len(entries) > 1 else None
            variance_percent = (
                (variance * 100 / first_price).quantize(Decimal("0.01"))
                if variance is not None and first_price != 0
                else None
            )
            product_name, sku = item_names.get(key[1:], (f"Product {key[1]}", ""))
            trends.append(
                SupplierProductPriceTrend(
                    product_id=key[1],
                    product_name=product_name,
                    sku=sku,
                    variant_id=key[2],
                    price_points=[
                        SupplierPricePoint(
                            recorded_at=entry.recorded_at,
                            unit_price=entry.unit_price,
                        )
                        for entry in entries
                    ],
                    first_price=first_price,
                    latest_price=latest_price,
                    variance=variance,
                    variance_percent=variance_percent,
                )
            )

        reports.append(
            SupplierPerformance(
                supplier_id=supplier.id,
                supplier_name=supplier.name,
                purchase_order_count=len(supplier_orders),
                total_order_value=sum(
                    (order.order_value for order in supplier_orders), Decimal("0")
                ),
                on_time_delivery_rate=on_time_rate,
                on_time_delivery_count=on_time_deliveries,
                eligible_delivery_count=eligible_deliveries,
                fulfilment_accuracy=fulfilment_accuracy,
                quantity_ordered=quantity_ordered,
                quantity_accepted=quantity_accepted,
                price_trends=trends,
            )
        )
    return reports


def valuation_rows(
    db: Session, *, location_id: int | None = None
) -> tuple[list[ValuationRow], Decimal]:
    """Return live values using average cost, then active supplier catalog price."""
    from app.modules.stock import stock_positions

    positions = stock_positions(db, location_id=location_id)
    missing_cost_keys = {
        (position.product_id, position.variant_id)
        for position in positions
        if position.average_cost is None
    }
    catalog_costs = supplier_catalog_costs(db, product_keys=tuple(missing_cost_keys))

    rows = []
    total = Decimal(0)
    for position in positions:
        key = (position.product_id, position.variant_id)
        catalog_cost = catalog_costs.get(key)
        cost_not_set = position.average_cost is None and catalog_cost is None
        if position.average_cost is not None:
            unit_cost = position.average_cost
        elif catalog_cost is not None:
            unit_cost = catalog_cost
        else:
            unit_cost = Decimal(0)
        value = unit_cost * position.quantity
        rows.append(ValuationRow(position, unit_cost, value, cost_not_set))
        total += value
    return rows, total


def reorder_rows(db: Session, *, location_id: int | None = None) -> list[tuple[StockPosition, int]]:
    """Return at/below-threshold stock and its needed quantity to reach reorder-to."""
    return [
        (position, max(position.reorder_to_level - position.quantity, 0))
        for position in stock_positions(db, location_id=location_id)
        if position.quantity <= position.reorder_threshold
    ]


def sales_trend_rows(
    db: Session,
    *,
    start: datetime,
    end: datetime,
    location_id: int | None = None,
) -> SalesTrendReport:
    """Build the product ranking from sales totals, catalog rows and one stock read."""
    totals = {
        row.product_id: row
        for row in sales_totals_by_product(db, start=start, end=end, location_id=location_id)
    }
    catalog = product_catalog_items(db)
    products = {}
    for item in catalog:
        products[item.product_id] = {
            "sku": item.sku,
            "name": item.name,
            "brand": item.brand,
            "category_name": item.category_name,
            "inactive": not item.is_active,
        }

    positions = stock_positions(db, location_id=location_id)
    stock_by_product: dict[int, int] = {}
    for position in positions:
        stock_by_product[position.product_id] = (
            stock_by_product.get(position.product_id, 0) + position.quantity
        )

    rows = []
    for product_id, metadata in products.items():
        total = totals.get(product_id)
        if total is None and metadata["inactive"]:
            continue
        total = total or SalesTotalsByProduct(
            product_id=product_id,
            units_sold=0,
            units_returned=0,
            net_units=0,
            gross_amount=Decimal("0"),
            refunded_amount=Decimal("0"),
            net_amount=Decimal("0"),
        )
        rows.append(
            SalesTrendRow(
                rank=0,
                product_id=product_id,
                sku=metadata["sku"],
                name=metadata["name"],
                brand=metadata["brand"],
                category_name=metadata["category_name"],
                units_sold=total.units_sold,
                units_returned=total.units_returned,
                net_units=total.net_units,
                gross_amount=total.gross_amount,
                refunded_amount=total.refunded_amount,
                net_amount=total.net_amount,
                current_stock=stock_by_product.get(product_id, 0),
                inactive=metadata["inactive"],
            )
        )

    rows.sort(key=lambda row: (-row.net_units, -row.net_amount, row.name, row.product_id))
    ranked = []
    previous_key = None
    rank = 0
    for index, row in enumerate(rows, 1):
        key = (row.net_units, row.net_amount)
        if key != previous_key:
            rank = index
            previous_key = key
        ranked.append(SalesTrendRow(**{**row.__dict__, "rank": rank}))

    return SalesTrendReport(
        rows=ranked,
        units_sold=sum(row.units_sold for row in ranked),
        units_returned=sum(row.units_returned for row in ranked),
        net_units=sum(row.net_units for row in ranked),
        gross_amount=sum((row.gross_amount for row in ranked), Decimal("0")),
        refunded_amount=sum((row.refunded_amount for row in ranked), Decimal("0")),
        net_amount=sum((row.net_amount for row in ranked), Decimal("0")),
        products_with_sales=sum(row.units_sold > 0 for row in ranked),
        products_with_zero_sales=sum(row.units_sold == 0 for row in ranked),
    )


def sales_trend_table(
    db: Session,
    *,
    start: datetime,
    end: datetime,
    location_id: int | None = None,
) -> ReportTable:
    report = sales_trend_rows(db, start=start, end=end, location_id=location_id)
    return ReportTable(
        title="Sales Trend Report",
        columns=[
            "Rank",
            "Product / SKU",
            "Brand",
            "Category",
            "Units sold",
            "Returned",
            "Net units",
            "Gross amount",
            "Refunded amount",
            "Net amount",
            "Current stock",
            "Inactive",
        ],
        rows=[
            [
                str(row.rank),
                f"{row.name} ({row.sku})",
                row.brand,
                row.category_name,
                str(row.units_sold),
                str(row.units_returned),
                str(row.net_units),
                f"{row.gross_amount:.2f}",
                f"{row.refunded_amount:.2f}",
                f"{row.net_amount:.2f}",
                str(row.current_stock),
                "Yes" if row.inactive else "No",
            ]
            for row in report.rows
        ],
        filters=_location_filter(db, location_id)
        | {"Date range": f"{start:%Y-%m-%d} to {(end.date()).isoformat()}"},
        summary={
            "Units sold": str(report.units_sold),
            "Units returned": str(report.units_returned),
            "Net units": str(report.net_units),
            "Gross amount": f"{report.gross_amount:.2f}",
            "Refunded amount": f"{report.refunded_amount:.2f}",
            "Net amount": f"{report.net_amount:.2f}",
        },
        widths=[0.6, 3.2, 1.5, 1.8, 1, 1, 1, 1.4, 1.4, 1.4, 1, 0.8],
    )


def _variant_label(position: StockPosition) -> str:
    attributes = (
        ", ".join(f"{name}: {value}" for name, value in position.variant_attributes.items())
        if position.variant_attributes
        else ""
    )
    return " — ".join(part for part in (position.variant_sku, attributes) if part) or "—"


def _location_filter(db: Session, location_id: int | None) -> dict[str, str]:
    from app.modules.stock import location_name

    if location_id is None:
        return {"Location": "All locations"}
    return {"Location": location_name(db, location_id) or str(location_id)}


def valuation_table(db: Session, *, location_id: int | None = None) -> ReportTable:
    """The stock valuation report as shown on screen, ready to export."""
    rows, total = valuation_rows(db, location_id=location_id)
    return ReportTable(
        title="Stock Valuation Report",
        columns=[
            "Product / SKU",
            "Variant",
            "Location",
            "Quantity",
            "Unit cost",
            "Inventory value",
        ],
        rows=[
            [
                f"{row.position.product_name} ({row.position.sku})",
                _variant_label(row.position),
                row.position.location_name,
                str(row.position.quantity),
                "Cost not set" if row.cost_not_set else f"{row.unit_cost:.4f}",
                f"{row.value:.2f}",
            ]
            for row in rows
        ],
        filters=_location_filter(db, location_id),
        summary={"Total inventory value": f"{total:.2f}"},
        widths=[4, 3, 2.5, 1.2, 1.5, 1.8],
    )


def reorder_table(db: Session, *, location_id: int | None = None) -> ReportTable:
    """The reorder report as returned by the API, ready to export."""
    return ReportTable(
        title="Reorder Report",
        columns=[
            "Product / SKU",
            "Variant",
            "Location",
            "Quantity",
            "Reorder threshold",
            "Reorder-to level",
            "Suggested quantity",
        ],
        rows=[
            [
                f"{position.product_name} ({position.sku})",
                _variant_label(position),
                position.location_name,
                str(position.quantity),
                str(position.reorder_threshold),
                str(position.reorder_to_level),
                str(suggested),
            ]
            for position, suggested in reorder_rows(db, location_id=location_id)
        ],
        filters=_location_filter(db, location_id),
        widths=[4, 3, 2.5, 1.2, 1.5, 1.5, 1.5],
    )
