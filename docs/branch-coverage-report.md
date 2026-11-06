# Branch coverage report

Branch coverage from the final test run. Statement and function coverage are in
[`code-coverage-report.md`](code-coverage-report.md).

Coverage was measured over the full suite run (355 backend and 137 frontend tests, all passing).
The project sets no coverage target, so this report records the numbers and points out the gaps; it does not
grade them pass or fail.

## Summary

| Code base | Branches | Covered | Missed | Branch coverage |
|---|---:|---:|---:|---:|
| Backend (`backend/app`, coverage.py with `--cov-branch`) | 1240 | 881 | 359 | **71.0%** |
| Frontend (`frontend/src`, v8 provider) | 1638 | 1322 | 316 | **80.7%** |

How the two tools count differs, so the figures are not comparable or additive:

- **coverage.py** counts each possible jump from a line (for example the `if` taken and not taken) and reports a branch as
  partial when only one side ran. 277 branch points in the backend are partial; counted as individual jumps,
  359 of the 1240 never happened.
- **v8** counts the branch blocks the JavaScript engine reports (conditionals, `&&`/`||`/`??`, `if`/`else`, `switch` cases, default
  values), so the same source gives a different total.

Environment and commands are in [`code-coverage-report.md`](code-coverage-report.md#summary); the commands are the same
runs. The backend run uses `--cov-branch`; the frontend v8 report includes branches by default.

## Backend

29 files contain branches; 8 of them have every branch covered.

| Module | Branches | Covered | Missed | Partial | Branch coverage |
|---|---:|---:|---:|---:|---:|
| app (core) | 6 | 5 | 1 | 1 | 83.3% |
| audit | 22 | 22 | 0 | 0 | 100.0% |
| auth | 148 | 115 | 33 | 25 | 77.7% |
| notifications | 82 | 63 | 19 | 17 | 76.8% |
| product | 178 | 95 | 83 | 39 | 53.4% |
| purchasing | 194 | 143 | 51 | 45 | 73.7% |
| reporting | 92 | 81 | 11 | 11 | 88.0% |
| sales | 290 | 208 | 82 | 74 | 71.7% |
| stock | 228 | 149 | 79 | 65 | 65.4% |
| **Total** | 1240 | 881 | 359 | 277 | **71.0%** |

### Uncovered branches by file

Lowest branch coverage first. In the last column `a→b` means the jump from line `a` to line `b` never happened and
`a→exit` means leaving the function from line `a` never happened. Lines are in the file at commit `b769635`.

| File | Branches | Covered | Missed | Branch coverage | Branches never taken |
|---|---:|---:|---:|---:|---|
| `app/modules/auth/_internal/mail.py` | 6 | 1 | 5 | 16.7% | 21→24, 36→37, 36→38, 38→39, 38→40 |
| `app/modules/product/router.py` | 164 | 84 | 80 | 51.2% | 155→156, 157→158, 200→201, 263→264, 304→305, 304→306, 307→308, 307→311, 309→310, 309→311, 317→318, 324→325, 326→327, 329→330, 331→332, 334→350, 343→344, 352→353, 449→450, 452→453, 467→469, 511→512, 518→534, 532→534, 543→544, 543→555, 555→556, 555→567, 579→580, 583→588, 634→635, 634→636, 665→666, 665→667, 678→679, 678→680, 682→683, 682→694, 713→714, 713→715, 755→756, 755→757, 757→758, 757→759, 772→773, 782→783, 844→845, 844→846, 847→848, 847→849, 858→859, 858→860, 867→868, 867→869, 877→878, 877→890, 913→914, 915→916, 968→969, 973→974, 1175→1176, 1175→1177, 1219→1220, 1235→1236, 1239→1244, 1255→1256, 1255→1257, 1293→1294, 1316→1317, 1318→1320, 1320→1321, 1320→1322, 1335→1336, 1338→1339, 1396→1397, 1399→1400, 1423→1424, 1423→1425, 1426→1427, 1426→1428 |
| `app/modules/stock/service.py` | 176 | 110 | 66 | 62.5% | 174→175, 176→177, 178→179, 180→181, 201→202, 214→215, 270→271, 272→273, 274→275, 276→277, 279→280, 281→282, 308→322, 325→327, 339→340, 357→358, 369→370, 397→398, 415→416, 417→418, 419→420, 443→445, 480→484, 484→478, 531→532, 550→569, 552→553, 567→550, 569→570, 588→589, 591→592, 626→631, 632→633, 635→636, 664→665, 679→680, 755→756, 773→774, 819→820, 825→826, 861→862, 863→872, 873→874, 875→876, 881→882, 982→983, 984→985, 1110→1111, 1112→1113, 1116→1117, 1117→1118, 1117→1121, 1122→1123, 1122→1145, 1136→1137, 1136→1142, 1140→1136, 1140→1141, 1142→1143, 1142→1161, 1157→1158, 1157→1159, 1159→1160, 1159→1161, 1254→1255, 1302→1303 |
| `app/modules/purchasing/service.py` | 16 | 11 | 5 | 68.8% | 223→224, 225→226, 233→234, 237→238, 245→246 |
| `app/modules/sales/router.py` | 72 | 50 | 22 | 69.4% | 326→327, 378→379, 409→410, 414→415, 456→457, 461→462, 469→493, 563→564, 646→647, 649→650, 652→653, 755→760, 756→757, 760→761, 760→762, 766→771, 777→778, 820→821, 823→824, 886→887, 889→890, 934→935 |
| `app/modules/purchasing/router.py` | 62 | 44 | 18 | 71.0% | 35→36, 151→152, 166→170, 166→171, 209→210, 286→287, 323→325, 351→352, 353→354, 366→367, 366→368, 394→395, 470→471, 470→474, 520→521, 523→524, 525→526, 567→568 |
| `app/modules/sales/service.py` | 188 | 134 | 54 | 71.3% | 136→137, 142→143, 145→146, 149→150, 152→153, 155→156, 160→161, 165→166, 178→179, 192→193, 224→225, 227→228, 231→232, 235→236, 239→240, 243→244, 259→260, 261→262, 261→268, 262→263, 262→266, 425→430, 496→503, 512→513, 521→522, 528→529, 565→566, 572→573, 590→619, 598→599, 617→590, 619→620, 717→718, 748→749, 790→791, 904→905, 908→909, 912→913, 916→917, 918→919, 923→924, 976→977, 985→986, 990→991, 1026→1027, 1051→1052, 1068→1069, 1134→1143, 1143→1144, 1143→1145, 1273→1274, 1277→1278, 1281→1282, 1335→1343 |
| `app/modules/auth/router.py` | 86 | 62 | 24 | 72.1% | 171→170, 173→178, 179→185, 188→189, 198→200, 200→202, 230→232, 235→exit, 235→236, 285→297, 310→311, 324→325, 333→334, 348→349, 348→350, 411→412, 429→431, 431→433, 442→443, 449→473, 484→485, 491→493, 534→535, 536→537 |
| `app/main.py` | 4 | 3 | 1 | 75.0% | 47→49 |
| `app/modules/auth/service.py` | 8 | 6 | 2 | 75.0% | 189→191, 196→197 |
| `app/modules/stock/router.py` | 52 | 39 | 13 | 75.0% | 71→72, 136→137, 150→151, 153→154, 167→168, 199→200, 245→246, 249→250, 315→316, 325→337, 422→423, 425→426, 435→437 |
| `app/modules/purchasing/purchase_orders.py` | 116 | 88 | 28 | 75.9% | 68→69, 84→85, 102→103, 104→107, 122→123, 162→163, 203→204, 243→244, 257→258, 385→389, 386→387, 469→470, 482→483, 503→504, 506→507, 511→512, 517→518, 522→523, 527→528, 567→578, 613→627, 627→635, 686→687, 689→690, 735→736, 790→791, 794→797, 818→819 |
| `app/modules/notifications/_internal/service.py` | 64 | 49 | 15 | 76.6% | 15→16, 67→68, 109→110, 153→271, 203→205, 205→206, 205→271, 258→264, 268→269, 337→338, 368→369, 379→380, 418→421, 455→460, 457→458 |
| `app/modules/reporting/router.py` | 30 | 23 | 7 | 76.7% | 152→153, 164→165, 222→223, 266→270, 315→316, 340→341, 375→376 |
| `app/modules/notifications/router.py` | 18 | 14 | 4 | 77.8% | 88→95, 92→95, 100→115, 112→115 |
| `app/modules/product/service.py` | 14 | 11 | 3 | 78.6% | 162→163, 174→175, 207→208 |
| `app/modules/sales/documents.py` | 30 | 24 | 6 | 80.0% | 40→43, 49→50, 52→53, 76→77, 127→128, 155→157 |
| `app/modules/auth/_internal/reset.py` | 6 | 5 | 1 | 83.3% | 80→81 |
| `app/modules/auth/_internal/users.py` | 8 | 7 | 1 | 87.5% | 12→13 |
| `app/modules/reporting/service.py` | 38 | 35 | 3 | 92.1% | 139→141, 290→291, 404→405 |
| `app/modules/reporting/_internal/export.py` | 24 | 23 | 1 | 95.8% | 134→135 |

### Where the gaps are

Counts are never-taken branches per function, from the table above.

- **`product/router.py` (lowest, 51.2%).** 79 of its 80 never-taken
  branches are on lines no test executes: `update_variant` (10) and `_normalise_variant` (8), `update_category` (7), category attribute
  validation, update, create and delete (16), image upload, serving and delete (about 10), `_variant_duplicate` (4) and `update_product` (5).
- **`stock/service.py` (62.5%).** `adjust_stock` (17), `receive_serial_stock` (8),
  `consume_tracked_stock` (7), `receive_batch_stock` (6) and `move_tracked_stock` (5): the batch- and serial-tracked paths and the error cases of stock adjustment.
- **`sales/service.py` (71.3%).** `process_return` (15), `_prepare_lines` (10), `_validate_payments` (6), `record_sale` (6),
  and restoring returned batch units and serials (10): the rejection side of return, line and payment checks.
- **`auth/_internal/mail.py` (16.7%).** The SMTP delivery code is never run (see the code coverage report).

## Frontend

| Area (`frontend/src/...`) | Branches | Covered | Missed | Branch coverage |
|---|---:|---:|---:|---:|
| src (root) | 76 | 68 | 8 | 89.5% |
| modules/audit | 47 | 35 | 12 | 74.5% |
| modules/auth | 102 | 75 | 27 | 73.5% |
| modules/notifications | 163 | 117 | 46 | 71.8% |
| modules/product | 114 | 86 | 28 | 75.4% |
| modules/purchasing | 357 | 286 | 71 | 80.1% |
| modules/reporting | 136 | 119 | 17 | 87.5% |
| modules/sales | 313 | 248 | 65 | 79.2% |
| modules/stock | 232 | 203 | 29 | 87.5% |
| shell | 38 | 34 | 4 | 89.5% |
| shell/components | 54 | 48 | 6 | 88.9% |
| utils | 6 | 3 | 3 | 50.0% |
| **Total** | **1638** | **1322** | **316** | **80.7%** |

Files with uncovered branches, lowest first:

| File | Branches | Covered | Missed | Branch coverage |
|---|---:|---:|---:|---:|
| `src/main.tsx` | 1 | 0 | 1 | 0% |
| `src/shell/NotificationBell.tsx` | 2 | 1 | 1 | 50% |
| `src/utils/date.ts` | 6 | 3 | 3 | 50% |
| `src/modules/product/CategoriesPage.tsx` | 17 | 9 | 8 | 52.94% |
| `src/modules/product/ProductFormPage.tsx` | 20 | 11 | 9 | 55% |
| `src/modules/notifications/useNotifications.ts` | 35 | 22 | 13 | 62.85% |
| `src/modules/auth/UsersPage.tsx` | 68 | 43 | 25 | 63.23% |
| `src/modules/purchasing/POReceivingPage.tsx` | 61 | 40 | 21 | 65.57% |
| `src/shell/AppLayout.tsx` | 3 | 2 | 1 | 66.66% |
| `src/modules/notifications/links.ts` | 23 | 16 | 7 | 69.56% |
| `src/modules/sales/DocumentPages.tsx` | 17 | 12 | 5 | 70.58% |
| `src/modules/notifications/NotificationsPage.tsx` | 49 | 35 | 14 | 71.42% |
| `src/modules/audit/AuditLogPage.tsx` | 47 | 35 | 12 | 74.46% |
| `src/shell/DashboardPage.tsx` | 4 | 3 | 1 | 75% |
| `src/modules/purchasing/SuppliersPage.tsx` | 89 | 67 | 22 | 75.28% |
| `src/modules/sales/DocumentView.tsx` | 54 | 41 | 13 | 75.92% |
| `src/modules/notifications/NotificationPanel.tsx` | 49 | 38 | 11 | 77.55% |
| `src/modules/sales/ReturnsPage.tsx` | 99 | 78 | 21 | 78.78% |
| `src/shell/components/Breadcrumb.tsx` | 5 | 4 | 1 | 80% |
| `src/shell/components/ConfirmDialog.tsx` | 20 | 16 | 4 | 80% |
| `src/api.ts` | 36 | 29 | 7 | 80.55% |
| `src/modules/sales/PosPage.tsx` | 108 | 87 | 21 | 80.55% |
| `src/modules/stock/BatchRecallPage.tsx` | 31 | 25 | 6 | 80.64% |
| `src/modules/product/ProductListPage.tsx` | 26 | 21 | 5 | 80.76% |
| `src/modules/sales/AvailabilityPage.tsx` | 29 | 24 | 5 | 82.75% |
| `src/modules/purchasing/PurchaseOrdersPage.tsx` | 157 | 131 | 26 | 83.43% |
| `src/modules/reporting/SupplierPerformanceReportPage.tsx` | 60 | 51 | 9 | 85% |
| `src/modules/notifications/api.ts` | 7 | 6 | 1 | 85.71% |
| `src/modules/product/ProductSearchPage.tsx` | 22 | 19 | 3 | 86.36% |
| `src/modules/product/ProductFilters.tsx` | 24 | 21 | 3 | 87.5% |
| `src/modules/reporting/StockValuationPage.tsx` | 40 | 35 | 5 | 87.5% |
| `src/modules/stock/StockTransferPage.tsx` | 74 | 65 | 9 | 87.83% |
| `src/modules/stock/LocationsPage.tsx` | 45 | 40 | 5 | 88.88% |
| `src/shell/components/SearchBox.tsx` | 9 | 8 | 1 | 88.88% |
| `src/modules/stock/StockLevelsPage.tsx` | 82 | 73 | 9 | 89.02% |
| `src/shell/usePopover.ts` | 10 | 9 | 1 | 90% |
| `src/modules/reporting/LowStockReportPage.tsx` | 36 | 33 | 3 | 91.66% |
| `src/modules/auth/AuthContext.tsx` | 13 | 12 | 1 | 92.3% |
| `src/modules/auth/LoginPage.tsx` | 15 | 14 | 1 | 93.33% |
| `src/modules/purchasing/SupplierPriceHistoryPage.tsx` | 31 | 29 | 2 | 93.54% |

**The frontend figure is optimistic.** v8 records branch data only for code that ran. A file that no test renders
(`ProductViewPage`, `CategoryAttributesPage`, `ForgotPasswordPage`, `ResetPasswordPage`, `SalesTrendReportPage`) reports 0
branches, shows 100% here, and adds nothing to the total, although its statement coverage is near zero. Read the branch
figures together with [`code-coverage-report.md`](code-coverage-report.md). The backend figure has no such gap, because
coverage.py analyses every file in `backend/app` whether or not a test imports it.
