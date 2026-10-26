# Recurring invoice drafts — local build

Local schema: `0008_recurring_drafts`. Nothing in this package is deployed and
no background scheduler is running.

Open **Products, stock & documents → Recurring**. Owners/admins create a series
from an existing invoice document. The system stores a snapshot of its parties,
lines, prices, taxes and terms. Subsequent catalogue edits do not silently rewrite
that snapshot. Users must review the generated drafts before issue.

Series support weekly or monthly intervals, a start date, optional last date,
payment terms and a unique five-character prefix. Monthly schedules retain their
original anchor day, clamping only for shorter months. Generated numbers include
the scheduled date and a monotonically increasing four-digit sequence.

**Generate due drafts** creates at most 25 drafts per request. Missed cycles remain
due for another bounded batch. Repeated runs do not duplicate completed cycles.
Pausing prevents generation without losing the next cycle. Ended/exhausted series
cannot be resumed. A series conflict is reported without advancing its cycle.

Every generated document is a **draft**: no invoice receivable, stock movement,
payment or customer message is posted. Current business approval policy applies
when a draft is later issued. The basic invoice creation route also rejects direct
posting when independent approval is enabled.

## Job entrypoint

The same authorized generation function is available to an explicitly invoked job:

```bash
cd backend
# SAAS_DATABASE_URL and CASH_PILOT_JOB_ACTOR must be configured securely.
python jobs.py --organization-id <business-id>
```

The configured actor must currently have write membership in that business.
Importing the module installs no timer, remote job or queue. Scheduler deployment,
credentials and operational monitoring remain separate work requiring later review.
Job output contains counts; it does not print connection strings or raw exceptions.

## Verification

Automated checks cover leap years/month ends, interval arithmetic, bounded catch-up,
repeat runs, end dates, numbering conflicts, pause, roles and foreign references.
The local browser created a series, generated one due draft, and generated zero on
replay. Posted invoice count and stock balances stayed unchanged; no browser page
errors occurred. PostgreSQL serialization still requires the dedicated integration
test noted in the build register.
