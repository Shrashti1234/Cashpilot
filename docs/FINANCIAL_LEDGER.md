# Financial ledger — local build

Implemented locally, not deployed. Local development schema now requires
`0007_invoice_ledger`. The hosted application remains unchanged.

Open a business → **Adjustments & statements**. Select an invoice to inspect
its original amount, internal credit/debit memos, recorded receipts, completed
external refunds, remaining amount due and customer credit.

## Accounting rules

- Adjusted charge = original invoice + debit memos − credit memos.
- Net received = posted receipts − recorded external refunds.
- Outstanding = max(adjusted charge − net received, 0).
- Customer credit = max(net received − adjusted charge, 0).
- Adjustments cannot make the charge negative or exceed INR 2 crore per invoice.
- A refund record cannot exceed that invoice's customer credit. It requires
  owner/admin access and confirmation that the refund already happened externally.
- No API in this module executes a payment, initiates a refund, returns stock or
  issues a legally certified GST credit/debit note. Internal memos are labelled
  accordingly; statutory note generation remains part of the unfinished tax work.

Invoice row locks serialize payments, memos and refunds in PostgreSQL. Each memo
number is unique within its business/type. Repeating an identical memo or refund
request has no additional effect; changed-payload replays fail. Runtime database
access to the new ledgers is SELECT/INSERT only.

The adjusted balances feed invoice lists, summaries, payment validation, collection
priorities, Decision Lab and customer statements. Adjusted/refunded invoices are
excluded from payment-delay training features rather than treating credits as
successful cash settlement. Refund records do not become learned operating costs.

Customer statements preserve invoice-level credits instead of silently reallocating
them to unrelated invoices. CSV/JSON exports require an explicit user action. CSV
exports neutralize spreadsheet-formula prefixes in user-controlled text.

## Local verification

Tests cover conservation, excess-credit/refund rejection, payment caps, idempotency,
role and tenant checks, downstream inference amounts, late responses after changing
tenants, exact decimal input and refund confirmation. All 71 backend and 33 frontend
tests and the TypeScript/Vite build passed for this work package.

The disposable local browser/database run started from a 29,575-paise invoice:
20,000 receipt, 15,000 credit, 2,000 completed-refund record, 5,000 debit, then 1,575
receipt. Final adjusted charge and net received were both 19,575 paise; outstanding,
customer credit and statement net due were zero. No browser page errors or mobile
horizontal page overflow were observed. Test identity overrides remained outside
the application repository; no hosted credentials or data were used.

Actual PostgreSQL concurrency testing is still pending because the local Docker
engine was unavailable. SQLite tests establish accounting and authorization logic,
not production row-lock behavior. Provider-initiated refunds and regulated tax
notes remain incomplete, rather than being represented by successful fake calls.
