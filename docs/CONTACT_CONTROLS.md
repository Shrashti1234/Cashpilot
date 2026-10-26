# Local consent, reminder drafts and completed contact history

Implemented locally. No delivery provider is configured and no message has been
sent. The interface distinguishes a draft from a completed external contact.

Owners/admins record customer preferences for email, WhatsApp and phone, with
unknown/granted/revoked status, evidence and optional expiry. Each change creates
an append-only evidence snapshot. These are business-recorded statements, not
independent verification of consent or legal compliance.

Writers can request a reminder draft for an issued invoice. Drafts are blocked by
missing/revoked/expired channel consent, a zero outstanding balance, a future due
date, an unresolved issue, a current unfulfilled payment commitment, or a contact
within three calendar days. The cooldown spans every invoice and channel for the
customer. The text uses the current adjusted balance and asks for correction if
the customer already paid. Preparing/copying it does not record contact or send.

Writers separately log contacts already completed outside CashPilot, explicitly
confirming that fact. Dates cannot be in the future. Replay keys prevent duplicate
recording. The log remains available when another reminder is blocked, permitting
honest historical recording. It is not evidence of provider delivery. Collections
recommendations now respect these customer-wide contact dates. Business dates use
Asia/Kolkata, including collection-plan and invoice-summary dates.

Viewers can read preferences and history; accountants can prepare drafts and log
completed contacts but cannot grant consent. All records use tenant checks,
composite tenant foreign keys and audit events. PostgreSQL grants deny modification
or deletion of completed contact history and consent-change snapshots.

Verified with 105 backend tests, including nine actual PostgreSQL checks, and 52
frontend tests. Local Edge verified blocked consent → grant evidence → exact INR
draft → synthetic completed contact → cooldown. Mobile width 390 had no page
overflow and no page errors. No real customer was contacted; the browser fixture
and authentication override are external to the production application.

Pending: real provider account and sandbox checks, message templates and required
provider approvals, recipient verification, direct opt-out callbacks, actual
delivery/retry/idempotency verification, scheduling, bounce/complaint handling,
applicable policy review and selected-language message translations. The manual
workflow does not mark the provider-reminder roadmap complete.
