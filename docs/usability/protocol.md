# ESIMS usability session protocol

**Classification: SESSION MATERIALS.** This protocol is for real sessions with consenting
cashier and staff participants. No participant session has been run for this review.

## Purpose and integrity

The session checks whether a new cashier or staff member can complete the basic tasks in NFR-10
without help. The facilitator must record observations rather than fill gaps with guesses. Use only
the participant id and role in the results file; do not record names, faces, or real customer data.

## Participants

Recruit 3–5 people for each role where possible. Participants should have no prior knowledge of
ESIMS. Experience using a shop till or inventory tool is useful but must be recorded honestly in
`prior_experience`. A participant may stop at any time without giving a reason.

Read this two-minute introduction word for word:

> We are checking the ESIMS system, not testing you. I will give you tasks that a cashier or stock
> staff member might receive. Please think aloud as you work. I will not help or hint while you
> work, but you may stop at any time. I will record a participant id, your role, task outcome,
> time, errors, and your ease rating. Do not enter real customer information. After each task I
> will ask one ease question from 1 to 7, where 1 is very difficult and 7 is very easy. Do you
> consent to taking part?

Record consent separately from the CSV. Do not record personal data. A screen or face recording
requires separate agreement and is not required by this protocol.

## Session setup

Before each session:

1. Reset the throwaway database:
   `docker compose down -v; docker compose up -d --build; docker compose run --rm backend alembic upgrade head`
2. Seed it:
   `docker compose run --rm backend python -m scripts.seed`
3. Use the seeded password from `.env` for `cashier`, `staff`, and other accounts as needed.
4. Open the app in a clean browser profile at `http://localhost:5173/login`.
5. Confirm the participant id, role, browser, date, and an empty observation sheet.

The reset removes local Docker volumes. Never use a production database.

## Facilitator rules

- Start the timer when the task statement is finished and stop it when the success criterion is
  met or the task is abandoned.
- Do not help, point, rephrase, or answer questions about where to click. Any hint makes the
  result `with_hint`, even if the participant later succeeds.
- Abandon a task after five minutes and record `failed`.
- Record errors and confusion in the participant's own words where possible; do not interpret
  them as a participant quote unless they said them.
- Ask after every task: “On a scale from 1 to 7, how easy was that task?” Record the number.
- At the end ask: “What was the hardest or least clear part of the system?” Record the answer
  without adding an explanation.

After each session, save the observation rows, record any consent withdrawal, and reset the
database before another participant.

## Key tasks

The task statements are scenarios and deliberately do not name menu items or buttons.

| ID | Role/account | Seeded starting state | Scenario | Expected path | Success criterion | Unaided |
|---|---|---|---|---|---|---|
| C1 | Cashier | `cashier`; Main Street Store has seeded products and stock | A customer wants to buy two Galaxy S24 phones and pay in cash. Record the sale and give them the invoice number. | Sign in, locate the product, add quantity two, take payment, complete the sale, read the invoice number. | Sale is recorded and the participant identifies the invoice number. | No facilitator hint or navigation instruction. |
| C2 | Cashier | `cashier`; seeded catalog includes variant SKUs | A customer wants one Galaxy S24 Black 128GB and one 65W USB-C Charger. Record both items in one cash sale. | Sign in, find each product or SKU, add both lines, check quantities, complete the sale. | Both intended lines and quantities appear on the recorded sale. | No hint; scanner-style SKU entry may be used if available. |
| C3 | Cashier | `cashier`; first create a sale in the seeded database | A customer returns one item from the invoice you just created because they changed their mind. Process the return and give the credit-note number. | Find the invoice, select one returnable unit, choose the reason, process the return, read the credit note. | Return is recorded for one unit and the credit-note number is identified. | No hint. |
| C4 | Cashier | `cashier`; invoice/print support from #26 is merged | A customer needs a paper copy of the invoice for the sale you just recorded. Print the receipt. | Open the recorded invoice and use the document print action. | The browser print dialog is opened or the participant reaches the printable invoice. | No hint. |
| S1 | Staff | `staff`; assigned location is Central Warehouse with seeded stock | A supervisor asks you to check how many Galaxy S24 units are at your location. | Sign in and locate the product's stock at the assigned location. | Participant reports the correct visible quantity and location. | No hint. |
| S2 | Staff | `staff`; seeded stock at Central Warehouse | The count is three units lower than the system quantity for the Galaxy S24. Remove three units and record “cycle count correction” as the reason. | Find the item, open the adjustment form, enter -3 and the reason, submit. | Quantity changes by -3 and the reason is recorded; no other location is changed. | No hint. |
| S3 | Staff | `staff`; at least one receivable seeded purchase order must exist for this session | A delivery has arrived for the selected purchase order. Receive all outstanding units and record any discrepancy if the delivery is short or damaged. | Open the receivable order, enter accepted/damaged/short quantities, add a discrepancy note when needed, submit. | Receipt is recorded and the order status/remaining quantities update correctly. | No hint. |
| S4 | Staff | `staff`; two locations and stock available for a transfer | Move two available Galaxy S24 units from the assigned location to another allowed location. | Choose source, item, destination and quantity, submit. | Transfer succeeds and source/destination quantities change correctly. | No hint. |

For C4, #26 is merged on `upstream/main`, so the task is not blocked. If a future checkout does
not include #26, mark C4 “blocked until #26 is merged” rather than implementing printing here.

## Observation sheet

Enter one row per participant-task in [session-results.csv](./session-results.csv). Use
`unaided`, `with_hint`, or `failed` for `success`; use seconds for `time_seconds`; and use a
number from 1 to 7 for `seq_1_to_7`.

## Browser checklist for NFR-9

This is a manual checklist, not a claim that the browsers were tested in this review. For the
latest supported version of each browser, repeat C1–C4 and S1–S4 using keyboard-only navigation:

| Browser | Login | Cashier tasks | Staff tasks | Focus/focus visibility | Result/notes |
|---|---|---|---|---|---|
| Latest Chrome | [ ] | [ ] | [ ] | [ ] | |
| Latest Firefox | [ ] | [ ] | [ ] | [ ] | |
| Latest Edge | [ ] | [ ] | [ ] | [ ] | |

## Summary script

The script has no built-in sample data. The compose service mounts only `backend` at `/app`, so
mount the docs directory read-only for a real run:

```powershell
docker compose run --rm --no-deps -v "${PWD}\docs\usability:/tmp/usability:ro" backend `
  python -m scripts.usability_summary /tmp/usability/session-results.csv
```

An empty file prints `No sessions have been run yet.`. The script rejects malformed rows with a
non-zero exit code and a clear message.
