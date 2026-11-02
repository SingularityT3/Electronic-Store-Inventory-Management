# Admin guide

Read [getting-started.md](getting-started.md) first. Admins can do everything a Manager can (see
[manager.md](manager.md)) and also manage user accounts and read the audit log. Installing,
configuring, backing up and monitoring the server are in [admin-setup.md](admin-setup.md).

## User accounts and roles (UC-02)

Open **Administration > User management**. The list shows each account's **Name**,
**Username**, **Email**, **Role**, **Location** and **Status**.

### What each role can do

| Capability                                        | Admin | Manager | Staff        | Cashier      |
| ------------------------------------------------- | :---: | :-----: | :----------: | :----------: |
| User management, audit log                        | ✓     |         |              |              |
| Products, categories, variants, locations         | ✓     | ✓       |              |              |
| View stock levels, batch recall                   | ✓     | ✓       | own location |              |
| Adjust and transfer stock                         | ✓     | ✓       | own location |              |
| Suppliers, price history, create and manage POs   | ✓     | ✓       |              |              |
| Receive POs                                       | ✓     | ✓       | own location |              |
| Record sales and returns, sales history           | ✓     | ✓       |              | own location |
| Approve returns older than 30 days                | ✓     | ✓       |              |              |
| Reports and exports                               | ✓     | ✓       |              |              |
| Product search                                    | ✓     | ✓       | ✓            | ✓            |
| Low-stock / PO notifications                      | ✓     | ✓       | stock, own location |       |

The server enforces this whatever the screen shows: a blocked request is refused and recorded in
the audit log as "Unauthorized access attempt".

### Add a user

1. Click **Add user**.
2. Fill in **Name**, **Username** and **Email** (both must be unique), and choose the **Role**.
3. For **Staff** and **Cashier**, choose their **Location** (their store or warehouse). Managers
   and Admins work across all locations.
4. Click **Create user**. The user is emailed a link to set their own password (valid 30 minutes;
   they can request a new one with **Forgot password?**). No password is ever emailed or shown.

A duplicate email or username, or a missing field, is shown next to the field and nothing is
saved. If your server has no email set up, set the first password on the server instead (see
[admin-setup.md](admin-setup.md#4-users-and-passwords-without-email)).

### Change a role or location

Click **Edit**, change **Role** or **Location**, and click **Save changes**. It applies from the user's next click;
there is no need to recreate the account.

### Deactivate, reactivate, unlock

- **Deactivate** stops the user signing in and ends their open sessions. Accounts are never
  deleted, so their sales and audit history stay attributable. **Reactivate** restores access.
- You cannot deactivate or demote yourself or the last active Admin.
- An account locked after 5 failed sign-ins unlocks by itself after 15 minutes; **Unlock**
  (shown on locked accounts) unlocks it now.

Every create, edit, deactivate, reactivate and unlock is written to the audit log with the
before and after values.

## Audit log (UC-03)

Open **Administration > Audit log**. Each entry shows **When**, **User**, **Module**, **Action**,
the **Record** it concerns and **Details**, with old and new values where something changed (for
example a price edit). Entries cover sign-ins (and failed and denied ones), sign-outs, user
changes, product and price changes, stock adjustments, transfers and receipts, purchase orders,
sales, returns and late-return approvals, exports, and denied access attempts.

Filter by **User**, **Action**, **Module**, **From** and **To**, then **Apply** (**Clear** resets).
Newest entries are first; use **Previous** / **Next** to page.

The log cannot be edited or deleted by anyone, including Admins; the database itself rejects
changes. Only Admins can open it.

## Everything else

Products, categories, locations, suppliers, purchase orders, receiving, sales, returns and
reports work exactly as for a Manager: see [manager.md](manager.md).
