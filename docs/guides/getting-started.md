# Getting started (all users)

ESIMS runs in a web browser (the latest two versions of Chrome, Firefox or Edge) on a desktop or
laptop. Your Admin gives you the web address and creates your account.

Pick the guide for your role after reading this page:

| Role    | What you do                                                   | Guide                      |
| ------- | ------------------------------------------------------------- | -------------------------- |
| Cashier | Sales, returns, receipts, product search                      | [cashier.md](cashier.md)   |
| Staff   | Stock levels, adjustments, transfers, receiving deliveries    | [staff.md](staff.md)       |
| Manager | Catalog, suppliers, purchase orders, reports, plus the above  | [manager.md](manager.md)   |
| Admin   | Users and the audit log, plus everything a Manager does       | [admin.md](admin.md)       |

Staff and Cashiers work at one store or warehouse (their assigned location) and only see that
location's stock, sales and alerts. Managers and Admins see every location.

## Your first sign-in (UC-01)

1. When your account is created you get an email with a link to set your password. Open it and
   choose a password of at least 8 characters. The link works once and expires after 30
   minutes; if it has expired, use **Forgot password?** below to get a new one.
2. Open the ESIMS address. On **Sign in to continue**, enter your **Username or email** and
   **Password**, then click **Sign in**.
3. You land on your dashboard. **Common tasks** lists shortcuts for your role.

If your store does not use email, your Admin sets your first password and gives it to you in
person.

### If you cannot sign in

- **"Invalid username or password"**: check both and try again. The message does not say which
  one was wrong, on purpose.
- After **5 wrong attempts in a row** the account is locked for **15 minutes**, even if the next
  password is right. Wait, or ask an Admin to unlock it.
- **Account disabled**: ask an Admin.
- **Forgot password?** on the sign-in page: enter your username or email and click **Send reset
  link**. You get an email if the account exists (the page does not say whether it does).

### Sessions

You are signed out after **30 minutes without activity** and after **12 hours** at most, and then
asked to sign in again before anything is saved. Sign out yourself with the user menu (your name,
top right) > **Sign out**, especially on a shared counter computer. After signing out, the
browser's Back button does not show protected pages.

## The screen

- **Header**: the ESIMS name, the notification bell (Admin, Manager and Staff), and the user menu
  with your name, role and **Sign out**.
- **Menu** (left): only the screens your role may use, in groups (Catalog, Inventory, Purchasing,
  Sales and returns, Reporting, Administration).
- **Content**: the screen you opened. Tables show "No ... found" when nothing matches; error
  messages appear next to the field or at the top of the form.

If you open a link to a screen your role cannot use, you see **Access denied**. That is expected;
ask a Manager if you need the task done.

## Notifications (UC-19)

Admins, Managers and Staff get in-app notifications; Cashiers do not.

- **Low stock / Out of stock**: an item at your location reached its reorder threshold, or zero.
  Staff see only their own location's alerts.
- **Purchase order status**: Submitted, Partially Received, Received, Cancelled. These go to the
  Manager who created the order and to Admins.

Click the bell to see the latest 10. The number on the bell is how many are unread. For each one:

- **View product** / **View order** opens it (and marks it read);
- **Create PO** (Managers and Admins, on stock alerts) opens a new purchase order already filled
  in with the item, location and a suggested quantity;
- **Mark as read** or **Dismiss** (removes it from the list).

A stock alert disappears by itself when the stock is back above the threshold. Notifications stay
until you dismiss them or the problem is resolved, also across sign-outs. **View all
notifications** at the bottom of the panel lists every notification, with an **All / Unread**
filter.

## Product search (UC-16)

Every role can search the catalog: **Catalog > Product search** (Managers and Admins use
**Catalog > Products**, which has the same search).

1. Type part of a product name, a SKU (any case, e.g. `ph-gal-s24`), a brand or a category name in
   **Search products** and click **Search**. Searching a category also finds products in its
   subcategories.
2. Narrow the list with **Category**, **Min price** / **Max price** and **Stock** (In stock, Low
   stock, Out of stock), then **Apply filters**. **Sort by** orders by name, price or stock.
3. **Clear** / **Clear filters** start again. "No products found" means nothing matched: try fewer
   words.

The price and stock shown are live. Staff and Cashiers see the stock at their own location.
