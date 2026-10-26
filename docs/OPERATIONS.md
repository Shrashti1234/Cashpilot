# Business operations — local build

This module is implemented locally and **has not been deployed**. Apply Alembic
through `0006_trade_operations` to a local development database. Hosted staging
remains at `0005_audit_events` until deployment is approved.

Open a business, then **Products, stock & documents**.

1. Owners/admins save the business legal name, address, state/UT code and optional
   GSTIN. GSTIN validation checks syntax and state prefix, not online registration.
2. Add products/services with SKU, unit, HSN/SAC, unit price, GST rate and optional
   stock tracking/reorder threshold. Archive products instead of deleting history.
3. Owners/admins record counted opening stock as a signed adjustment with a reason.
   The stock ledger is append-only for the runtime database role. Negative balances
   are rejected; corrections use compensating movements.
4. Create an estimate, purchase order or invoice draft with up to 100 line items,
   quantities to three decimal places, discounts, explicit tax/cess rates and party
   details. Saving a draft does not affect stock or receivables.
5. Review and issue. If independent approval is enabled, a different owner/admin
   must approve first. A posted invoice creates its receivable and stock deductions
   in one transaction. Insufficient stock rolls back the entire issue.
6. Receive purchase-order lines partially or fully. Repeating the same request key
   has no additional effect. Over-receipts and changed-payload replays are rejected.
   Purchase orders and stock receipts do not create a cash payment or expense.
7. Copy estimates to invoice drafts, print the selected document, download its JSON
   snapshot or export the catalogue as CSV. Snapshots retain historical business and
   line details when the profile/catalogue changes.

All endpoints are under `/api/v1/organizations/{id}/operations`. Every endpoint
checks membership; viewer writes are denied. Profile/stock adjustments/approvals
require owner or admin. Product updates, drafts, issuing and receipts permit
accountants. PostgreSQL product row locks serialize stock writes; document locks
serialize issue and receipt transitions. Actual concurrent PostgreSQL behavior
still needs a dedicated integration test; SQLite cannot establish that guarantee.

## Tax workbench scope

Calculations use integer paise and explicit basis-point rates. Fractional quantities
round line gross amounts half up to paise. Intra-state central and state/UT components
round independently; inter-state IGST and cess round per line. Purchase-order tax
uses the vendor's state, rather than the business purchaser's state.

The [CBIC invoice particulars](https://cbic-gst.gov.in/gst-invoice-rules.html) informed
the fields. This module does not certify tax classification, eligibility, GSTIN
registration or legal compliance. E-invoice IRNs, e-way bills, reverse-charge/export
special cases, statutory tax return formats and signature verification remain
explicitly incomplete. Rates are supplied and reviewed by the user.

## Verification

Automated tests cover tax conservation, fractional units, foreign references,
permissions, independent approvals, immutable snapshots, atomic stock/invoice issue,
receipt replay and over-receipt. Schema creation/rollback and ORM parity pass.

The local browser used a disposable migrated SQLite database and explicit test
identity overrides outside the application repository. It verified profile →
catalogue → stock adjustment → partial/final purchase receipts → invoice issue →
API/database response. A 2.5-unit invoice at INR 100.25 with 18% intra-state tax
posted exactly 29,575 paise, and stock reconciled to 9,500 milliunits. Desktop,
390px mobile and print layouts were inspected; no page errors or horizontal page
overflow were observed. This is local fixture evidence, not hosted Auth or external
provider verification.
