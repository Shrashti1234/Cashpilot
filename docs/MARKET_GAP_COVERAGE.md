# CashPilot 2.0 — Comprehensive Market-Gap Coverage Register

**Status:** Long-term product requirements and acceptance criteria, beyond the current ML portfolio release. This is not a claim that every listed feature has shipped.

The deployed release now includes authenticated workspaces, customers/invoices/partial payments, operating-cash CSV imports and corrections, dispute lifecycle, audit history, trained synthetic-data models and 7/30/90-day Decision Lab scenarios. See [current verification](DEPLOYMENT_VERIFICATION.md) and [model limitations](MODEL_CARD.md). The matrix below records the larger market-gap scope, which is only partially covered.

## Definition of done
Every feature requires: functional UI, authenticated and organization-scoped backend, persistent data model and migrations, input validation, permission checks, automated tests, accessibility, observability, and documentation. Integrations require sandbox verification and credential management. Regulatory functionality requires review against current official requirements before launch.

## Release gates
- **Gate 0 — Safety foundation:** verified identity provider; organization onboarding and role permissions; PostgreSQL migrations; tenant isolation (including background jobs, files, WebSockets); audit trail; secrets management; backup/restore drills; rate limiting; secure deployment.
- **Gate 1 — Financial operations:** customers, products, estimates, GST-aware invoices, line items, credit/debit notes, recurring invoices, partial payments, refunds, expenses, purchase orders, basic inventory, customer statements, export/import.
- **Gate 2 — Get paid:** receivables aging, consent-based reminders, promises to pay, contact cooldown, payment links, reconciliation, invoice disputes, buyer portal with expiring scoped access, attachments and evidence, collection analytics.
- **Gate 3 — Cash intelligence:** scheduled-cash forecast, scenario simulator, shortage alerts, explainable prioritization, recommended actions, forecast-vs-actual, customer concentration, seasonal patterns, optional ML only after validation and monitoring.
- **Gate 4 — India MSME workflows:** GSTIN/Udyam onboarding, GST invoice validation, e-invoicing/e-way-bill integration where applicable, accountant collaboration, delayed-payment timeline and evidence pack, official dispute-channel guidance, TReDS readiness and integrations subject to partner access.
- **Gate 5 — Accessibility and distribution:** Hindi/English and regional localization, mobile-responsive PWA, offline draft sync/conflict handling, consent and opt-out controls for email/WhatsApp, integrations with existing accounting software and banks through approved providers.
- **Gate 6 — Enterprise quality:** fine-grained permissions, maker-checker approvals, multi-branch, webhook signatures, event delivery retries, data retention/deletion/export, performance tests, disaster recovery, operational monitoring.

## Traceability matrix
| Gap | Deliverable | Acceptance test | State |
| --- | --- | --- | --- |
| Fragmented micro and B2B workflows | Organization modes, roles, onboarding | Cross-tenant and cross-role access denied | Domain foundation only |
| No unified invoice-to-cash workflow | Customer, invoice, payment, expense records | Invoice balance updates on payment | Domain/API foundation only |
| Unclear cash shortfalls | Forecast + actionable rescue plan | Explainable shortage date and what-if alternatives | Forecast primitive only |
| Collections without context | Priority queue, contact history, promises | Cooldown and dispute-aware recommendations | Priority primitive only |
| Invoice disputes handled off-platform | Dispute lifecycle, attachments, audit trail | Authorized buyer/supplier can resolve with evidence | Domain foundation only |
| Buyers lack transparency | Scoped buyer portal | Buyer sees only explicitly shared invoices | Not started |
| Complex tax compliance | GST workflows and export | Validate tax calculations against reviewed cases | Not started |
| No MSME delayed-payment guidance | Evidence pack and deadline guidance | Official rules and caveats reviewed | Not started |
| Financing readiness friction | TReDS eligibility checklist | No financing promise; partner integration tested | Not started |
| Unreliable customer payment forecasts | Explainable scenarios, uncertainty bands | Backtesting, drift monitoring | Not started |
| Weak accessibility | Localized mobile/offline workflow | Usability and sync tests | Not started |
| Tool fragmentation | Accounting, payments, banking integrations | Sandbox reconciliation and webhook tests | Not started |
| Weak operational controls | Audit, backups, monitoring | Restore drill and incident playbook | Not started |

## Implementation policy
- Do not treat a competitor capability as absent without validating the latest product offering.
- Avoid misleading claims of AI accuracy, payment guarantees, creditworthiness, legal outcomes, or tax compliance.
- No automatic customer outreach without consent, approval, and opt-out controls.
- Never deploy the existing unauthenticated demo backend publicly.
- Keep work in feature branches until CI, security review, and migration review pass.
- Each release must include a demo and explicit list of incomplete features.

## Next engineering sequence
1. Verified authentication and PostgreSQL migrations.
2. Connect tenant-safe API routers to authenticated application.
3. Buyer portal and invoice dispute workflow.
4. Cash Rescue Engine and scenario simulator.
5. Billing, GST and integrations in independently testable increments.
