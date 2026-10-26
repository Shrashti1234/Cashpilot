# Full-project completion register

User scope confirmed: **entire market-gap roadmap**. No further deployments,
remote migrations, pushes that trigger preview builds, paid provisioning or
outreach until the full project is reviewed and deployment is explicitly approved.
Existing hosted staging is an older reference, not the completion target.

## Acceptance rule

A feature is complete only with tenant-safe persistence, a usable interface,
validation, role checks, meaningful tests, documentation and local verification.
An external integration additionally needs an actual provider sandbox check.
Placeholders and simulated successes do not satisfy this rule.

## Work packages

| Package | Required work | Current state |
| --- | --- | --- |
| Identity and organizations | Auth, roles, membership administration, invitations, branches | Auth/onboarding and local account-bound invitations, roles, revocation and last-owner protection implemented; branches pending |
| Financial operations | Products, estimates, invoice items, tax workbench, notes, recurring invoices, refunds, expenses, purchase orders, stock, statements and imports/exports | Basic customers/invoices/payments/cash imports implemented; extended operations in progress |
| Collections | Aging, promises, consent/cooldown reminders, payment links, reconciliation, buyer portal, evidence and analytics | Priorities and supplier dispute review implemented; remaining workflows pending |
| Cash intelligence | Scheduled and learned forecasts, scenarios, alerts, forecast-versus-actual, concentration, seasonality, drift | Trained synthetic models and Decision Lab implemented; operational analytics pending |
| India workflows | Business registrations, tax validation, e-invoice/e-way-bill adapter, delayed-payment evidence, reviewed official guidance, TReDS readiness | Pending; external/regulatory verification required |
| Accessibility | Complete selected translations, PWA, offline drafts and conflict handling, mobile and keyboard checks | Responsive base UI; full accessibility/offline/localization pending |
| Integrations | Accounting import/export, bank ingestion, payment provider, messaging provider, consent/opt-outs | Cash CSV only; actual provider setup and sandbox validation pending |
| Enterprise controls | Permissions, independent approvals, branches, signed/retried events, retention/export/deletion, monitoring, backup restoration, load/recovery tests | Tenant checks and append-only runtime audit implemented; remaining controls pending |

## Implementation order

1. Financial records: catalogue, stock ledger, purchase orders, estimates,
   line-item tax drafts and issued invoice integration. **Implemented locally**:
   catalogue/create/edit/archive, stock adjustments and history, partial purchase
   receipts, estimates/copy-to-invoice, tax components, immutable document snapshots,
   independent approval policy, atomic invoice/stock posting, print/JSON/CSV export.
   See [operations verification](OPERATIONS.md). [Real local PostgreSQL concurrency
   and database restore checks](POSTGRES_VERIFICATION.md) now pass. The remaining
   regulated/provider financial workflows still need completion.
2. Complete financial lifecycle: **internal credit/debit memos, records of completed
   external refunds, customer statements and downstream adjusted balances are
   implemented locally**. See [ledger verification](FINANCIAL_LEDGER.md).
   [Recurring invoice draft series](RECURRING_DRAFTS.md), manual generation and a job
   entrypoint are also implemented locally. An installed scheduler, statutory GST
   note generation and actual payment-provider refunds remain pending.
3. Collaboration and approvals: [local team administration](TEAM_ACCESS.md) now
   supports a second approver and access revocation. [Private buyer invoice access
   and payment commitments](BUYER_ACCESS.md) are implemented locally. [Private
   invoice record bundles](INVOICE_EVIDENCE.md) now export related application
   records with integrity checksums. Original attachments, branches and broader
   approval rules remain pending.
4. [Manual statement reconciliation](BANK_RECONCILIATION.md) is implemented locally:
   preview/import, duplicate protection, exact one-to-one matching to existing
   ledger records, reversal history and matched-cash edit protection. Live bank
   ingestion, advanced settlements, payment and reminder provider integrations
   still require actual sandboxes. [Local contact preferences and reminder drafts](CONTACT_CONTROLS.md)
   now include consent evidence/history, opt-outs, promise/dispute suppression,
   customer-wide cooldowns and completed external-contact records. No delivery
   provider is connected and no customer message has been sent.
5. [Local overview, aging and concentration](BUSINESS_OVERVIEW.md) are implemented,
   with recorded cash/expense charts, low-stock/review queues and factual attention
   flags. [The local forecast journal](FORECAST_JOURNAL.md) now preserves dated
   outlooks, compares completed windows with recorded expenses, invalidates reviews
   after record changes, and supports optional conditional cash-threshold attention.
   Installed scheduling, notification delivery, statistical drift and real-world
   validation remain pending.
6. India-specific workbench, evidence exports and integration checks.
7. Localization, offline/PWA and enterprise operations.
8. Full local acceptance run and review. Deployment is a separate approval.

Current local checkpoint: 114 backend tests (including eleven PostgreSQL checks),
57 frontend tests and frontend build pass. CI remains unpushed.
Hosted recovery configuration and object-storage recovery remain unfinished.

Progress must be recorded against acceptance criteria, not inferred from the
presence of a button or an API route. Model validity on real business data and
regulated partner access cannot be manufactured by code or synthetic tests.
