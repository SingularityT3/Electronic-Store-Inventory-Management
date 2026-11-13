# Handover

ESIMS (Electronics Store Inventory Management System) as of the development freeze in November
2026. This page is the starting point for whoever runs or continues the system.

## What is delivered

A web application for one or more electronics stores and warehouses: product catalog with
categories and variants, per-location stock with adjustments, transfers and batch/serial
tracking, suppliers and purchase orders with receiving, point of sale with invoices and returns,
in-app notifications, four reports with CSV/PDF export, user accounts with four roles, and an
immutable audit log. All 41 issues on the project board are implemented; the requirement IDs
for each are in the issue and in [`backend/tests/TRACEABILITY.md`](../backend/tests/TRACEABILITY.md).

Stack: FastAPI (Python 3.12), React + TypeScript (Vite), PostgreSQL 16, all in Docker. Production
runs behind Caddy with automatic HTTPS, plus a daily backup job and an uptime monitor.

## Where everything is

| What | Where |
| --- | --- |
| Source code | https://github.com/SingularityT3/Electronic-Store-Inventory-Management (`main`) |
| Requirements and design: SRS, SAD (architecture and design), security requirements, test plan, use case diagram and flows | [`Documents/`](../Documents) (`*.docx`); SRS Appendix A holds the design decisions |
| User guides per role | [`docs/guides/`](guides/getting-started.md): [Cashier](guides/cashier.md), [Staff](guides/staff.md), [Manager](guides/manager.md), [Admin](guides/admin.md) |
| Installation, configuration, first accounts, operations | [`docs/guides/admin-setup.md`](guides/admin-setup.md), [`docs/deployment.md`](deployment.md) |
| Backups and recovery plan | [`docs/backup-recovery.md`](backup-recovery.md) |
| Monitoring and uptime reporting | [`docs/monitoring.md`](monitoring.md) |
| Record retention | [`docs/retention.md`](retention.md) |
| Architecture, module rules, API notes | [`docs/architecture.md`](architecture.md), [`docs/schema.md`](schema.md) |
| Performance and load test | [`docs/performance.md`](performance.md), [`docs/performance-results.md`](performance-results.md) |
| Usability review | [`docs/usability/`](usability/report.md) |
| Test plan traceability (226 cases) | [`backend/tests/TRACEABILITY.md`](../backend/tests/TRACEABILITY.md) |
| Developer setup, tests and lint | [`README.md`](../README.md), [`CLAUDE.md`](../CLAUDE.md) |
| Work history | GitHub issues #1 to #41 and their pull requests; project board "Electronics Store Inventory management System" |

## Access to hand over

These are held by the team, not stored in the repository. Transfer each one and record who holds
it now.

| Item | Notes |
| --- | --- |
| GitHub repository admin rights | Needed to merge, manage branch protection and Actions secrets. |
| Production server login (SSH) and the `esims` folder on it | Where `docker compose ... up` runs. |
| `.env.prod` | Database password, SMTP credentials, alert channels. Keep an offline copy; it is not in the backups. |
| Backup storage (`BACKUP_PATH`) | NAS or share credentials; the backups are needed for any restore. |
| DNS for `SITE_ADDRESS` | Moving the server means updating this record. |
| SMTP account | Sends invite and reset links. |
| Alert channels and external uptime checker | Email list / webhook in `MONITOR_*`; the external checker account. |
| First Admin account in the app | Create further Admins in User management and deactivate leavers. |

## Verification at handover

Done on 2 November 2026 on a clean Docker host:

- Development setup from `README.md` alone: empty volumes, `docker compose up`, migrate, seed;
  health check and every role's screens load.
- Production stack from `admin-setup.md`: `.env.prod` from the example, `db`, `migrate`,
  `backend`, `monitor` and `web` up and healthy; HTTPS with HTTP redirect; first Admin from
  `scripts.create_admin`; locations and users created in the app; passwords set with
  `scripts.set_password` (no SMTP); a category, product, supplier, purchase order, receipt and
  sale; invoices show the configured store name and GSTIN; a stopped database raised a DOWN
  alert within a minute and a Recovered alert after. The `backup` image could not be built in
  that environment (its package mirror was blocked); its restore drill is recorded in
  `backup-recovery.md`.
- The four role guides were followed step by step in a browser (Chromium) against the running
  app: 19 core tasks, from adding a serial-tracked product to a sale by serial number, a return,
  report exports and creating a user. All passed.
- Automated tests: 355 backend and 137 frontend tests pass; lint, formatting and module-boundary
  checks are clean. 223 of the 226 test plan cases are automated; the other 3 are manual with a
  reason in the traceability table.
- Load test at 10,000 SKUs: all 18 checks pass (p95 under 1 s for search, list, filter and sort;
  no overselling under concurrent sales).

## Decisions on open questions

The SRS left these open; they were settled with the team and are recorded in SRS Appendix A and
the issues.

| Topic | Decision |
| --- | --- |
| Return window (A-1, A-11) | 30 days. Older returns need a Manager signing in on the cashier's screen; the approver is logged. Damaged returns are refunded but never restocked. |
| Record retention (A-2) | 8 years, configurable upwards only, enforced by the database. India (INR, GST) assumed; confirm the GST rules at go-live. |
| Unit cost (A-3) | Weighted average cost, updated on each receipt; supplier catalog price before the first receipt; otherwise "cost not set" and zero value. |
| Reorder quantity (A-4) | Reorder-to level minus stock; reorder-to defaults to twice the threshold. |
| Who sells and returns (A-5) | Cashier, Manager, Admin. Staff cannot. |
| Notifications (A-6) | Stock alerts to Admin, Manager and Staff of that location; PO status to the creating Manager and Admins; none to Cashiers. Supplier-facing notifications are out of scope. |
| PO lifecycle (A-7) | Draft, Submitted, Partially Received, Received; Cancelled only before any receipt; lines lock once receiving starts; over-receipt rejected. |
| Location scoping (A-9) | Staff and Cashiers see and act on their own location only. |
| Transfers (A-10) | Staff, Manager and Admin; atomic; logged. |
| Lockout and sessions (A-12) | 5 failures lock for 15 minutes (Admin can unlock); sessions end after 30 idle minutes or 12 hours. |
| Security scope | Of the derived security requirements, the team accepted five: SEC-AUTH-2, SEC-SES-4, SEC-DAT-6, SEC-INP-2, SEC-INP-3 (issue #41). |
| GST | One rate (`GST_RATE`, 18%) for every product, applied after line discounts and rounded per line. |
| Dates | Report periods and the return window use UTC calendar days; there is no store time zone setting. |
| Invoice numbers | From a database sequence: unique and increasing, but a rolled-back sale leaves a gap. |
| Refunds | Each returned unit refunds its share of what the customer paid (after discount, with GST); partial returns add up exactly to the line total. |

## Known limitations

- **No sessions with real users yet.** The usability review (#38) is an expert review; its
  criterion "most test users complete each key task unaided" needs 3 to 5 cashiers and staff to
  run the protocol in `docs/usability/protocol.md`. Rendering was checked in Chromium only;
  Firefox and Edge need the manual checklist in the usability report.
- **Email is needed for self-service passwords.** Without SMTP an operator sets passwords with
  `scripts.set_password`.
- **Batch and serial items**: an adjustment can only remove stock and the system chooses the
  units (oldest batch first); a specific damaged serial cannot be picked. Extra units come in on
  a purchase order. The tracking mode of a product cannot change once it has stock history.
- **One currency and one GST rate** for all products; no per-category tax.
- **UTC dates** for reports and the return window (see above).
- **Large PDFs**: the full 50,000-row valuation report takes 10 to 15 s as a PDF; CSV takes
  about 2 s.
- **Monitoring** runs on the same server, so an external checker is needed to catch the server
  itself going down.
- **Test plan**: three cases are manual (dashboard refresh timing FR2.2-ST-2, and the two
  10,000-SKU timings FR7.1-ST-1 and FR7.2-ST-1, which the nightly load test measures instead).
- **Code structure**: a few modules (`sales`, `stock`, `purchasing`, `reporting`) keep their
  implementation in `service.py`, `purchase_orders.py` or `documents.py` instead of `_internal/`.
  The import-linter contracts still hold; moving the code is a refactor for later.

## Suggested next steps

1. Run the user sessions and browser checklist from the usability review; file what they find.
2. Merge the open pull requests, then enable branch protection on `main` (required checks:
   `backend`, `frontend`, `production-build`, `secret-scan`).
3. Do the yearly restore drill on the production backups and record it in
   `backup-recovery.md`.
4. Confirm the GST and retention rules with the store's accountant before go-live.
