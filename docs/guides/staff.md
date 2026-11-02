# Staff guide

Read [getting-started.md](getting-started.md) first. Your menu has **Dashboard**, **Product
search**, **Stock levels**, **Stock adjustment**, **Stock transfer**, **Batch recall** and **PO
receiving**. You work on your assigned store or warehouse: you see its stock and alerts, adjust
it, transfer out of it and receive deliveries into it. You cannot record sales or returns.

## View stock levels (UC-07)

Open **Inventory > Stock levels**. Each row is one item (a product, or one variant of it) at your
location: **Quantity** on hand, **Reorder threshold**, and **Combined total** across locations.
Narrow the list with **Category** and **Product**. "No stock levels match these filters" means
nothing matched.

## Adjust stock (UC-08)

Use this for damage, loss, theft, or a count that does not match the system. Every adjustment is
logged with your name and reason.

1. Open **Inventory > Stock adjustment** (it opens Stock levels) and find the item.
2. Click **Adjust** on its row. The form shows the item, the location and the current quantity.
3. **Quantity change**: a negative number removes stock (e.g. `-2` for two damaged units), a
   positive number adds it (e.g. `5` found during a count).
4. Choose the **Reason type** and write the **Reason** (required), e.g. "Dropped in the
   stockroom".
5. Click **Adjust stock**. Click **Cancel** to close without saving.

The new quantity shows immediately and also counts in the stock valuation report. The system
refuses an adjustment that would take stock below zero ("Adjustment would result in negative
stock") or that has no reason ("Reason is required for stock adjustment"); stock is then left
unchanged. Your filters stay as they were, so you can adjust the next item straight away.

For **batch- or serial-tracked** items an adjustment can only remove stock (the system picks the
units, oldest batch first); extra units must arrive through a PO receipt ("Tracked stock must be
registered through a receipt").

If stock reaches its reorder threshold, a low-stock alert appears on the bell for you and the
Managers.

## Transfer stock to another location (UC-20)

1. Open **Inventory > Stock transfer**.
2. Choose your own location as **Source location** (Staff can only transfer out of their own),
   then the **Product or variant**, the **Destination location** and the **Quantity**.
3. Click **Transfer stock**.

Both locations change together: the source goes down and the destination goes up, or nothing
changes. You cannot transfer more than the source has, to the same location, or a quantity of
zero or less.

## Receive a delivery against a purchase order (UC-12)

1. Open **Purchasing > PO receiving**. It lists submitted and partially received orders for your
   location ("No purchase orders are waiting to be received" if there are none).
2. Click the PO number on the delivery note. Each line shows what is still **Outstanding**.
3. For each line enter what arrived:
   - **Accepted**: good units that go into sellable stock;
   - **Damaged**: arrived broken, not added to stock;
   - **Short**: missing from the delivery;
   - **Discrepancy note**: required when anything is damaged or short, e.g. "2 cartons crushed".
   For a complete, undamaged delivery click **Accept all outstanding** to fill every line.
4. Batch-tracked items: type the **Batch number** printed on the cartons. Serial-tracked items:
   scan each unit into **Accepted serial numbers** (one per line), and damaged units into
   **Damaged serial numbers**. A serial number already in the system is rejected ("Duplicate
   serial number") and nothing is received.
5. Click **Record receipt**.

Only the accepted quantity is added, at the location on the PO. If something is still
outstanding the PO becomes **Partially Received** and stays in the list for the next delivery;
when everything has arrived it becomes **Received**. You cannot receive more than is outstanding
("Received quantity exceeds outstanding order quantity").

## Batch recall lookup

If a supplier recalls a batch, open **Inventory > Batch recall**, type the **Batch number** and
click **Look up**. You see how many units of that batch were received, how many are still in
stock at your location, and which invoices the sold units went out on (with any returns). Put the
in-stock units aside with a stock adjustment and give the invoice list to a Manager.

## Notifications and product search

See [getting-started.md](getting-started.md#notifications-uc-19). **View product** on a stock
alert takes you to Stock levels. **Catalog > Product search** shows prices and your location's
stock.
