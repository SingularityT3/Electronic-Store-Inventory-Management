# Usability findings

**Classification: EXPERT REVIEW.** These findings come from inspecting the React code and
screen flows on 2026-11-01. They are not participant observations and contain no user-session
results.

Severity uses the Nielsen scale: **0** not a problem, **1** cosmetic, **2** minor, **3** major,
**4** usability catastrophe.

## U-01 — POS search did not support scanner-style Enter

- **Screen/route:** Record sale, `/sales`
- **Task affected:** C1, C2
- **Severity:** 3 (major)
- **Evidence:** `PosPage` rendered `SearchBox` with only `onSearch={setQuery}`. Search results
  appeared after submit, but an exact SKU or a single result was not added without a second
  click. Evidence: [PosPage.tsx](../../frontend/src/modules/sales/PosPage.tsx),
  [SearchBox.tsx](../../frontend/src/shell/components/SearchBox.tsx).
- **Why it matters:** A new cashier using a barcode scanner expects the scanner's Enter key to
  complete product selection; requiring a result click increases uncertainty and slows every line.
- **Recommended fix:** Focus the search input on entry and after an item is added, auto-add an
  exact SKU or the only matching result, and provide keyboard shortcuts.
- **Status:** Fixed in this change with `frontend/src/modules/sales/PosPage.test.tsx::scanner-style Enter adds the only matching product and refocuses search`.

## U-02 — Dashboard gave no role-specific starting guidance

- **Screen/route:** Dashboard, `/`
- **Task affected:** C1–C4, S1–S4
- **Severity:** 3 (major)
- **Evidence:** [DashboardPage.tsx](../../frontend/src/shell/DashboardPage.tsx) only welcomed the
  user and referred to the sidebar. It had no task-oriented starting points.
- **Why it matters:** A first-time cashier or staff member must translate job language into menu
  labels before beginning.
- **Recommended fix:** Add a permission-filtered Common tasks region while retaining the sidebar.
- **Status:** Fixed in this change with `frontend/src/shell/shell.test.tsx::the dashboard shows role-specific common tasks`.

## U-03 — POS completion shortcut and error announcement were absent

- **Screen/route:** Record sale, `/sales`
- **Task affected:** C1, C2
- **Severity:** 2 (minor)
- **Evidence:** Completion was a mouse-oriented button and the top-level error used `role="alert"`
  without an explicit live-region assertion; there was no visible shortcut hint.
- **Why it matters:** Keyboard-only cashiers need a predictable way to finish and to notice a
  server-side line error.
- **Recommended fix:** Add Alt+S and Alt+Enter hints/handlers and an assertive live region.
- **Status:** Fixed in this change with `frontend/src/modules/sales/PosPage.test.tsx::Alt shortcuts focus search and complete a sale`.

## U-04 — PO receiving has no receive-all convenience action

- **Screen/route:** PO receiving, `/purchase-orders/receive`
- **Task affected:** S3
- **Severity:** 2 (minor)
- **Evidence:** [POReceivingPage.tsx](../../frontend/src/modules/purchasing/POReceivingPage.tsx)
  requires quantities to be entered line by line; no “receive all remaining” action is present.
- **Why it matters:** A normal complete delivery can require repeated data entry and creates more
  opportunities for a new staff member to miss a line.
- **Recommended fix:** Add a tested receive-all action after confirming the product rules for
  damaged, short, batch and serial-tracked lines.
- **Status:** Open.

## U-05 — Stock adjustment form does not retain the selected context after success

- **Screen/route:** Stock levels, `/stock` and `/stock/adjust`
- **Task affected:** S2
- **Severity:** 2 (minor)
- **Evidence:** [StockLevelsPage.tsx](../../frontend/src/modules/stock/StockLevelsPage.tsx)
  reloads data after an adjustment, but the review found no explicit persistence requirement for
  the selected location/category/product filters.
- **Why it matters:** Repeated corrections may require re-finding the same item.
- **Recommended fix:** Preserve the selected filters when refreshing after a successful adjustment.
- **Status:** Open.

## U-06 — Browser and visual contrast verification is still outstanding

- **Screen/route:** All key task screens
- **Task affected:** C1–C4, S1–S4
- **Severity:** 1 (cosmetic/verification)
- **Evidence:** Source inspection can verify labels and landmarks, but cannot verify the latest
  Chrome, Firefox and Edge rendering or actual contrast without running those browsers.
- **Why it matters:** NFR-9 explicitly names those desktop browsers.
- **Recommended fix:** Run the manual checklist in [protocol.md](./protocol.md) and record results.
- **Status:** Open.
