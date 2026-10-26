# Local independent financial approvals

Owners can require independent approval for internal credit/debit memos and
records of externally completed refunds. Enabling requires two active owner/admin
accounts. Policy changes are audited. Pending requests never post automatically
when a policy changes, and approval remains independent even when policy is optional.

When required, direct posting through financial-ledger endpoints is blocked. The
ledger interface displays the policy and directs users to Financial approvals.
Writers can submit memo requests; only owners/admins can submit completed-refund
records. Refund requesters must explicitly confirm completion outside CashPilot.
No step executes a bank/payment-provider transfer or creates statutory GST notes.

A different active owner/admin must approve. Current requester permissions are
checked again at decision time; deactivated/viewer requesters, or refund requesters
no longer holding owner/admin access, cannot have requests executed. The requester
or an owner/admin can cancel pending requests; administrators can reject them.
Decision notes are required. Viewers can read the queue but cannot decide or submit.

Approval revalidates current ledger limits and refund credit, posts the record and
stores the decision in one transaction. Failed revalidation leaves the request
pending and the ledger unchanged. Request/decision replays do not post duplicates.
Business control locks serialize policy/team changes and competing approvals.
PostgreSQL grants allow changing decision fields while denying changes to stored
request payload, requester identity and original invoice/operation/replay key.

Invoice evidence bundles now include `approvals.json`, related activity and ten
checksummed files. Request replay keys remain excluded. The latest queue shows
200 requests; large-scale filtering/pagination remains future work.

Verified with 119 backend tests (twelve actual PostgreSQL checks), 61 frontend
tests and production build. Tests cover direct-route bypass, self-approval,
roles/revocation, failed refund revalidation, successful credit-limited refund,
replays, concurrent decisions and database column grants. Local Edge used two
explicit fixture identities: owner submits → own approval unavailable → second
admin approves → exactly one 1,234-paise memo posts. Mobile width 390 had no page
overflow or page errors. These fixture overrides are outside production code.

No cloud change or actual refund was made. Remaining enterprise scope includes
branches, configurable finer permissions and approval thresholds, broader expense/
purchase/reconciliation approvals, retention controls and operational acceptance.
