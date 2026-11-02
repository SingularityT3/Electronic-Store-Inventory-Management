# Manager guide

Read [getting-started.md](getting-started.md) first. Managers see every location and can do
everything a Cashier and a Staff member can, so also use:

- [cashier.md](cashier.md) for sales, receipts and returns. On **Sales** you first choose the
  **Sale location**. You can approve late returns yourself, and you approve a cashier's late
  return by typing your username and password on their screen.
- [staff.md](staff.md) for stock levels, adjustments, transfers, receiving and batch recall,
  for any location.

This guide covers the catalog, locations, suppliers, purchase orders and reports.

## Products (UC-04)

**Catalog > Products** lists the catalog with search, filters and sort (see
[getting-started.md](getting-started.md#product-search-uc-16)).

**Add a product**

1. Click **Add product**.
2. Fill in **Product name** and **SKU** (required, the SKU must be unique), **Category**,
   **Brand**, **Price** (₹, not negative) and **Description**.
3. **Inventory tracking**: *Untracked* (sold by count), *Batch* (each delivery has a batch
   number) or *Serial* (each unit has its own serial number). Choose before the first delivery;
   it cannot change once the product has stock history.
4. Click **Add product**. You land on **Edit product** with "Product added successfully", where
   you can add pictures straight away. "SKU already exists" or a missing name keeps you on the
   form; nothing is saved.

**Edit, add images, change the price**: open the product, click **Edit**, change the fields and
click **Save changes**. Upload pictures under **Product image** (JPEG, PNG or WebP, up to 5 MB).
A new price is used for the next sale straight away; the old and new price are written to the
audit log. Invoices already issued keep their price.

**Delete**: click **Delete** in the list. A product that still has stock at any location cannot
be deleted ("Cannot delete product with existing stock"); adjust or transfer the stock out
first. Deleted products stay in sales history and reports.

## Categories and attributes (UC-05)

**Catalog > Categories** shows the category tree with the number of products in each category
and, in brackets, including its subcategories.

- **Add top-level category**, or **Add subcategory** on a row, then type the **Category name**.
  Names must be unique among siblings.
- **Rename / move** changes the name or the **Parent category**. A category cannot be moved under
  itself or one of its own subcategories. A rename shows everywhere at once.
- Click a category name to see its products, with a breadcrumb such as Electronics > Mobile
  Phones > Smartphones. **Delete category** works only when it has no subcategories and no
  products; move them first.
- **Manage attributes** defines the variant attributes for products in that category and its
  subcategories, e.g. **Attribute name** "Color" with **Allowed values** "Black, White, Blue".

## Variants (UC-06)

Open a product (or **Catalog > Variants** and pick one). Under **Variants**:

1. **Add variant**: a **SKU** of its own, a value for each attribute (e.g. Color Black, Storage
   128GB) and an optional **Variant price** (blank uses the product price).
2. Each variant has its own stock at each location and is chosen separately at the till.
3. The same combination twice is rejected ("Variant combination already exists"). Removing a
   variant leaves the product and the other variants unchanged. A product that already holds
   stock without variants must have that stock moved before its first variant is added.

## Locations

**Inventory > Locations**: **New location**, give the **Name**, **Type** (store or warehouse)
and **Address**, then **Add location**. **Edit** renames a location or marks it inactive. A new
location is available for stock, transfers, purchase orders and sales immediately. Assign Staff
and Cashiers to it from User management (Admin).

## Reorder settings and alerts (FR-2.3)

On **Stock levels**, **Reorder settings** on a row sets, for that item at that location:

- **Reorder threshold**: a low-stock alert is raised when stock is at or below it, and an
  out-of-stock alert at zero;
- **Reorder-to level**: what the reorder report suggests ordering up to. Leave it blank to use
  twice the threshold.

A change is checked at once: stock of 12 with a new threshold of 15 raises an alert immediately.
Alerts clear themselves when stock goes back above the threshold.

## Suppliers (UC-10)

**Purchasing > Suppliers**:

- **Add supplier**: **Name**, **Contact name**, **Email** (checked: "Invalid email format"),
  **Phone**, **Address**, then **Create supplier**.
- Click a supplier to edit it (**Save supplier**) and to manage its **product catalog**: choose
  a **Product or variant**, the **Supplier SKU** and **Supplier price**, then **Add catalog
  item**. A purchase order can only include items in the supplier's catalog.
- **Deactivate supplier** hides it from new orders. A supplier with open purchase orders cannot
  be removed ("Cannot delete supplier with open purchase orders"). Editing contact details never
  changes prices on existing orders.

**Purchasing > Supplier price history** lists the unit price of every receipt, oldest first,
filterable by **Supplier** and **Product**. Entries are permanent; use them to compare suppliers
before ordering.

## Purchase orders (UC-11)

**Purchasing > Purchase orders**.

**Create**

1. **New purchase order**. Choose the **Supplier**, the **Receiving location** and the **Expected
   delivery date**; add **Notes** if needed.
2. Pick a **Supplier catalog item** and click **Add line**; set its **Quantity** and **Unit
   price** (it starts at the catalog price). Repeat for each item. The **Order total** updates as
   you go. Quantities must be above zero.
3. **Create draft**. A draft can still be edited (**Save draft**).
4. **Submit purchase order** sends it: the status becomes **Submitted** and you get a notification. Staff at the
   receiving location can now receive it.

Shortcuts: **Create PO** on a low-stock notification, or on a row of the reorder report, opens a
new draft with the item, location and suggested quantity filled in; choose the supplier and
delivery date, then create it.

**Statuses**: Draft > Submitted > Partially Received > Received, or **Cancelled**. Click an order
in the list to open it. **Cancel purchase order** (and confirm) works only before anything has
been received; a cancelled order leaves the pending list. Once receiving has started the lines are locked ("Cannot modify PO
after receipt has started"). Receiving is described in [staff.md](staff.md#receive-a-delivery-against-a-purchase-order-uc-12);
each receipt updates the item's average cost and the supplier price history, and notifies you of
the new status.

## Reports (UC-17, UC-18)

**Reporting > Reports** opens the stock valuation report, with links to the other reports. Every
report has **Export CSV** and **Export PDF**: the file holds the same rows as the screen, and the
PDF header shows the report name, when it was generated and the filters. File names look like
`Sales_Trend_Report_2026-11-02.pdf`. If an export fails, click it again.

- **Stock valuation**: quantity x unit cost per item and location, and the **Total inventory
  value**. Choose one **Location** or all. Unit cost is the weighted average purchase cost,
  recalculated on every receipt; before the first receipt the supplier catalog price is used,
  and items with neither show **Cost not set** and count as 0.
- **Low-stock & reorder report**: every item at or below its threshold, by location, with the
  **suggested quantity** (reorder-to level minus current stock) and a **Create PO** link. It
  always matches the alerts on the bell.
- **Sales trend report**: products ranked by units sold in a **Period** (today, last 7 or 30
  days, this month, or custom dates) for one **Location** or all, best sellers at the top and
  worst (including no sales) at the bottom. Returns are subtracted from the period of the
  original sale. Click **Generate** after changing the filters.
- **Supplier performance** (Reporting > Supplier performance): for a **From** / **To** period and
  the **Suppliers to compare**, side by side: on-time delivery rate, number and value of orders,
  fulfilment accuracy (accepted / ordered, so short and damaged deliveries lower it) and the
  price trend of each product. Click **Generate report**.

Dates are whole days in UTC.

## Approving a late return

Returns more than 30 days after the sale need a Manager. On your own login the return goes
through directly. On a cashier's screen, the **Manager approval required** box asks for your
**Manager username** and **Manager password**; click **Approve**. You are recorded as the
approver. See [cashier.md](cashier.md#returns-older-than-30-days-manager-override).
