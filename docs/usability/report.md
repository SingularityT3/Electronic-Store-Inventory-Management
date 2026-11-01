# Usability review report

**Classification: EXPERT REVIEW and SESSION MATERIALS.** This report contains an expert
walk-through and templates for future real sessions. No representative user sessions have been
run, so it contains no invented participants, timings, quotes, success rates, or satisfaction
scores.

## Purpose and scope

Issue #38 checks NFR-10 (basic cashier/staff work after brief instruction without help) and NFR-9
(desktop web UI in current Chrome, Firefox and Edge). The key tasks are cashier product search,
single and multi-item sale, return, invoice printing, and staff stock view, adjustment, purchase
order receiving, and transfer.

## Method

An expert review was completed by inspecting the React components, routes, tests and keyboard
flows on 2026-11-01. A running browser session with Chrome, Firefox and Edge was not available
for this review, and no real users were observed. The session protocol and empty observation CSV
are provided for the team.

## Expert review findings and fixes

| Finding | Severity | Status |
|---|---:|---|
| U-01 POS scanner-style Enter | 3 | Fixed; focused POS test added |
| U-02 role-specific dashboard guidance | 3 | Fixed; dashboard test added |
| U-03 POS keyboard shortcuts/live error announcement | 2 | Fixed; focused POS test added |
| U-04 receive-all PO action | 2 | Open |
| U-05 retain stock adjustment context | 2 | Open |
| U-06 browser/contrast verification | 1 | Open |

Details and issue-ready text are in [findings.md](./findings.md).

## Keyboard and accessibility checks

The source review confirmed labelled inputs through `FormField`, a skip link, semantic headings,
named navigation, disabled submit buttons during requests, and existing `role="alert"`/status
feedback. The POS fix adds initial/refocus behavior, Escape clearing, Alt+S search focus,
Alt+Enter completion, and an assertive error live region. A real keyboard-only run and browser
screen-reader/contrast check could not be verified here.

## Click counts from the expert UI flow

These are **expert-review UI-flow counts**, not participant timings or results. They count
activation steps after login and exclude typing; a product/PO selection is one activation.

| Task | Before | After | Counting note |
|---|---:|---:|---|
| C1 single sale | 5 | 4 | Product search submit, result selection, complete sale, invoice action; after scanner Enter replaces result selection |
| C2 multi-item sale | 7 | 5 | Two product selections become two scanner Enter actions |
| C3 return | 5 | 5 | Invoice lookup, line selection, reason, process, document action |
| C4 print invoice | 2 | 2 | Open document and print; #26 is merged |
| S1 view stock | 2 | 2 | Open stock screen and identify row |
| S2 adjust stock | 5 | 5 | Open screen, adjust, quantity, reason, submit |
| S3 receive PO | 5+ | 5+ | One or more quantity fields per line; open finding U-04 |
| S4 transfer | 5 | 5 | Source, item, destination, quantity, submit |

## Results of user sessions

### Per-task summary

No sessions have been run yet. Run the summary script after collecting real rows; do not replace
this statement with estimates.

| Task | Attempts | Unaided success rate | With hint | Failed | Median seconds | Range seconds | Mean SEQ |
|---|---:|---:|---:|---:|---:|---|---:|
| No sessions have been run yet |  |  |  |  |  |  |  |

### Role verdict

No sessions have been run yet. The criterion “most test users complete each key task unaided” is
**OPEN** until the team collects and summarizes real session data.

| Role | Participants | Tasks | Verdict |
|---|---:|---:|---|
| No sessions have been run yet |  |  | Open |

## Acceptance criteria status

1. Most test users complete each key task unaided: **OPEN — user sessions have not been run.**
2. Report of findings and fixes committed: **Ready as uncommitted work in this change; commit and
   review it with the fixes.**

## Limitations

No representative users, participant quotes, task times, success rates, SEQ scores, or confusion
rates can be reported. The expert review did not verify rendering in the latest Chrome, Firefox,
or Edge, real barcode hardware, browser print dialogs, or screen-reader output.

## Next steps for the team

1. Run the protocol with 3–5 cashier and 3–5 staff participants.
2. Fill the CSV with one honest row per participant-task and run the summary script.
3. Complete the Chrome, Firefox and Edge checklist.
4. Create GitHub issues for the open findings U-04–U-06.
5. Update this report with the generated tables and update `backend/tests/TRACEABILITY.md` if
   NFR-9/NFR-10 rows are added to the test plan.
