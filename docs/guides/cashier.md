# Cashier guide

Read [getting-started.md](getting-started.md) first. Your menu has **Dashboard**, **Product
search**, **Sales**, **Returns** and **Sales history**. You sell from your assigned store only.

## Record a sale (UC-13)

Open **Sales and returns > Sales**. The store name is under **Record sale**.

1. **Find a product**: type a name or SKU and press **Enter** (or click **Search**). A barcode
   scanner that types the SKU and Enter works the same way. If exactly one item matches it goes
   straight into the cart; otherwise click the item you want. Each result shows its price and how
   many are available at your store.
   - A product with variants (colour, storage, ...) is listed once per variant, e.g.
     "Black / 128GB (PH-GAL-S24-BLK-128) — ₹74,999.00 — 3 available". Pick the one the customer
     is buying; its own price and stock are used.
   - For a serial-numbered item (TVs, laptops), the cart line has a **Serial numbers** box: scan or
     type the serial of each unit you hand over, one per line. The quantity follows the number of
     serials.
2. In **Cart**, set **Quantity** for each line, and a **Discount** if allowed (an amount in ₹ or
   a percentage, chosen next to the field). Remove a line you do not want.
3. Check the totals: **Subtotal**, **Discount**, **GST** (18%, added after the discount) and the
   total.
4. **Payment**: choose the **Method** (Cash, Card, UPI, Other). **Amount** is the sale total. For
   cash, type what the customer gave you in **Received** to see **Change due**. For card or UPI,
   put the transaction ID in **Reference**.
5. Click **Complete sale** (or press **Alt+Enter**). **Alt+S** jumps back to the search box.

The sale, the stock deduction and the invoice are saved together: either all of it happens or
none of it. You then see **Sale recorded** with the invoice.

- **"Out of stock"** / **"Insufficient stock"**: your store does not have enough. Lower the
  quantity or remove the line; another cashier may just have sold the last one.
- **"Payment amounts must equal the sale total"**: the Amount must match the total exactly.
- Click **New sale** for the next customer.

## Print or download the invoice (UC-15)

After the sale (or from **Sales history**), the invoice shows the invoice number (e.g.
`INV-0042`), date, cashier, each line with quantity, unit price and tax, the total and the
payment.

- **Print** opens your browser's print dialog.
- **Download PDF** saves a PDF copy. If it fails, click **Retry**, or **View on screen** to show the
  invoice instead.

An invoice never changes after it is issued, even if a price changes later.

## Find an earlier sale (Sales history)

Open **Sales and returns > Sales history**. Search by **Invoice number** (`INV-0042` or `42`),
or by **Date from** / **Date to**, and click **Search**. Click a sale to view and reprint its
invoice. A sale with returns is marked **Partially Returned** or **Fully Returned**; the
original invoice is never altered.

## Process a return (UC-14)

Open **Sales and returns > Returns**.

1. Enter the **Invoice number** from the customer's receipt and click **Look up**. "Invoice not
   found" means the number is wrong; nothing is processed.
2. The sale's lines show what was **Sold**, **Already returned** and is still **Returnable**. For
   each item coming back, set **Return quantity** (it cannot exceed what is returnable). For a
   serial-numbered item, tick the serial being returned.
3. Set the **Condition**:
   - **Resaleable**: goes back into sellable stock at this store.
   - **Damaged**: recorded and refunded, but **not** put back into sellable stock.
   Choosing the reason "Defective - not sellable" sets Damaged for you.
4. Fill in **Reason for return** (required) and any **Additional notes**.
5. Click **Process return**.

You get **Return processed** with a credit note (e.g. `CN-0007`), the refund total and whether
each item was restocked. **Print** or **Download PDF** it for the customer. The refund is the
item's share of what the customer paid, including GST and any discount.

### Returns older than 30 days (Manager override)

If the sale is more than 30 days old, the screen shows "Older than 30 days: Manager approval
required". When you click **Process return**, a **Manager approval required** box opens. A
Manager types their **Manager username** and **Manager password** on your screen and clicks
**Approve**; the return then completes and the Manager is recorded as the approver. Without
approval no return is recorded. Five wrong Manager passwords lock that Manager's account like a
normal sign-in.

## Product search

**Catalog > Product search** works as described in [getting-started.md](getting-started.md#product-search-uc-16)
and shows the stock at your store.
