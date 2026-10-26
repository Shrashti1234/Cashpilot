# Local PostgreSQL verification — 26 October 2026

No hosted database or deployment was changed. A dedicated PostgreSQL **17.11**
instance listened only on 127.0.0.1 with SCRAM passwords generated locally. Server
binaries came from the Windows archive linked by the [PostgreSQL project](https://www.postgresql.org/download/windows/).
Private fixture credentials stayed outside the repository and were not printed.

All migrations from `0001_saas_foundation` through `0009_team_access` applied
successfully. The runtime connected as the actual restricted `cashpilot_backend`
login, rather than using an administrator for application operations.

## Concurrent operations and privileges

| Check | Observed result |
| --- | --- |
| Two concurrent deductions of the last stock unit | One posted; one rejected; zero remaining; no overselling |
| Two simultaneous requests with the same payment key | Same payment ID; exactly one posted receipt |
| Two refunds competing for one customer credit | One recorded; one rejected; credit conserved |
| Competing invoice issues with insufficient stock | One issued; one remained draft; rejected issue left no receivable |
| Team-control lock with simultaneous audit FK insert | Audit insert completed while control lock remained held |
| Runtime audit UPDATE / invoice DELETE / stock DELETE / refund UPDATE | PostgreSQL rejected all with SQLSTATE 42501 |
| Browser-role financial SELECT privileges and runtime-role membership | Denied |
| Runtime global powers | No superuser/create-role/create-db/replication/RLS bypass/inheritance; connection limit 10 |
| RLS on all registered SaaS tables | Enabled |

Team and recurrence control paths now use PostgreSQL NO KEY UPDATE for their
organization lock. This serializes those control mutations while allowing the KEY
SHARE locks required by unrelated child/audit inserts, avoiding an unnecessary
foreign-key lock dependency. Product/invoice/document row locks retain their own
financial serialization.

RLS policies trust the backend role globally. They do not partition tenants inside
that role; authenticated membership and organization-scoped application queries
remain essential. Cross-tenant API denial is covered separately by the API tests.

## Actual backup/restore drill

`pg_dump` wrote a custom-format archive of a dedicated database containing only
synthetic fixtures. `pg_restore` restored it into a fresh, randomly named local
database. Checks through the runtime login confirmed:

- Original charge 12,345 paise, credit memo 1,000, receipt 2,345 → outstanding 9,000.
- Unicode customer text survived exactly.
- Audit records and Alembic revision survived.
- RLS and restricted browser/runtime permissions survived.

The restored database and fixture business records were removed after checking.
This proves a local database restore procedure. It does **not** establish hosted
Supabase backup availability, recovery objectives, object-storage restoration or
an incident-response drill; those remain in the completion register.

## Reproduce safely

The opt-in tests require two environment variables: `CASH_PILOT_PG_ADMIN_URL` and
`CASH_PILOT_PG_RUNTIME_URL`. Both must address the dedicated `cashpilot_checks`
database on loopback. Tests refuse hosted hosts or another database name, and
require the fixture marker before changing data. Keep credentials in private
environment configuration, never command arguments or repository files.

Set `CASH_PILOT_ALLOW_TEST_SETUP=1` and run `python prepare_test_postgres.py` to
initialize this explicitly isolated fixture and apply migrations. Matching dump
tools under `CASH_PILOT_PG_BIN_DIR` enable the restore test. Then run:

```bash
cd backend
python -m pytest -q
```

The completed local run passed **86 backend tests**, including all seven real
PostgreSQL tests and the restore drill. The frontend suite passed **42 tests** and
the production build passed. Without an opt-in database, the seven PostgreSQL
checks skip explicitly rather than reporting fake coverage.

A separate PostgreSQL CI job is prepared in the backend workflow. It creates
short-lived random fixture credentials, binds its database only to loopback and
cleans up its container. This workflow change remains local and has not run on
GitHub because pushes/deployments are paused. Its restore check skips unless
matching client tools are configured; the Windows local drill above did run.
