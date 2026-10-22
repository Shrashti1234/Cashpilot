# CashPilot SaaS architecture and implementation plan

Status: design proposal, not deployed. Current main branch is an unauthenticated local demo. **Never expose its API publicly or load real financial data.**

## Product
One multi-tenant application with `micro` and `b2b` business modes. Modes change navigation and features, not data isolation. Users can belong to multiple businesses.

## Stack
React + TypeScript + Recharts frontend; FastAPI + SQLAlchemy + Alembic backend; PostgreSQL; managed authentication with server-side JWT verification and membership checks; private object storage; background job worker and durable queue. Keep the existing transaction demo intact until migration is tested.

## Minimum data model
- users: id (identity-provider subject), email, created_at
- organizations: id, name, mode (micro/b2b), currency, timezone, created_at
- memberships: organization_id, user_id, role (owner/admin/accountant/viewer), unique(organization_id,user_id)
- customers: id, organization_id, name, email, phone, payment_terms_days
- invoices: id, organization_id, customer_id, invoice_number, issue_date, due_date, status, currency, subtotal_minor, tax_minor, total_minor, created_at, unique(organization_id,invoice_number)
- invoice_items: id, organization_id, invoice_id, description, quantity, unit_price_minor, tax_rate
- payments: id, organization_id, invoice_id, amount_minor, paid_at, method, external_reference, idempotency_key
- expenses: id, organization_id, amount_minor, category, due_date, paid_at
- audit_events: id, organization_id, actor_id, action, resource_type, resource_id, timestamp

All monetary values stored in minor units or fixed precision decimal, never float. Invoice balances derived from posted payments; do not duplicate mutable balances. Define statuses and transitions explicitly.

## Tenant security invariants
1. Every protected request authenticates the caller, resolves their active organization, and checks membership and role server-side.
2. Every read/write filters by organization_id; never trust a client-provided tenant ID without verifying membership.
3. Every child FK must be validated as belonging to the same organization, including customer_id and invoice_id.
4. Add PostgreSQL row-level security as defense-in-depth; test application role cannot bypass it.
5. WebSockets require authenticated, authorized tenant channels; remove current global broadcast before production.
6. File uploads private, validated, size-limited, malware-scanned where feasible, and accessed by short-lived signed URLs.
7. Encrypt in transit, protect secrets, rate-limit, audit privileged changes, enforce backups and restore tests.
8. Never expose sensitive customer/invoice information in logs or model prompts without consent and minimization.

## API v1 proposal
- GET /api/v1/me and GET /api/v1/organizations
- POST /api/v1/organizations; POST /api/v1/organizations/{id}/members/invitations
- GET/POST /api/v1/customers
- GET/POST /api/v1/invoices; GET/PATCH /api/v1/invoices/{id}
- POST /api/v1/invoices/{id}/payments
- GET/POST /api/v1/expenses
- GET /api/v1/dashboard/summary
- GET /api/v1/receivables/aging
- GET /api/v1/cashflow/forecast?days=30

## Forecast MVP
Start with transparent dated cash-in/cash-out schedules and scenario controls. Forecast expected invoice receipts using actual historical payment delays where available; label insufficient history and provide ranges. Do not call simple heuristics trained AI. Explain each forecast input.

## Delivery sequence
1. Add automated CI and pinned dependency lock strategy. Introduce Alembic migrations and PostgreSQL integration tests.
2. Integrate managed authentication and organization/membership authorization; add cross-tenant denial tests.
3. Migrate transactions to tenant-scoped records; replace global WebSocket broadcasting.
4. Implement customers, invoices, invoice items and partial payments with server-side validation.
5. Add expenses, aging buckets and deterministic forecast.
6. Add accessible micro/B2B layouts, onboarding, loading/empty/error states.
7. Add invoice extraction with human review; opt-in reminders and durable delivery logs.
8. Complete security review, operational monitoring, backup/restore drill, legal/GST review, and staged deployment.

## Definition of done for first production milestone
- Unauthenticated API calls rejected.
- Business A cannot access or mutate Business B's records via any endpoint or realtime channel.
- Owner/admin/accountant/viewer roles enforced and tested.
- Migration preserves existing demo data safely in a separate local development environment.
- CI tests pass; no real financial data or public deployment before security verification.
