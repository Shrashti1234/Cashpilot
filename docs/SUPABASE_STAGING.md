# CashPilot Supabase staging

Project: `cashpilot-db` (`gdjgmgfuzpqcedqgdozv`). PostgreSQL 17 is active.

The live database reports Alembic revision `0002_supabase_access` (verified 23 October 2026). RLS is enabled on the six SaaS tables and `alembic_version`. No browser-facing policies are installed because the FastAPI server enforces tenant authorization. The security advisor reports seven informational no-policy findings and no warning/error findings.

## Remaining deployment steps

1. Deploy the existing FastAPI Docker backend to a staging HTTPS host.
2. Set `SAAS_DATABASE_URL` in the backend host's secret manager using the Supabase Connect panel. Never commit or share database passwords.
3. Configure Supabase Auth using the dedicated SDK frontend and ES256/JWKS backend settings in [OIDC_SETUP.md](OIDC_SETUP.md). Database provisioning does not automatically configure authentication.
4. Configure the backend CORS allowlist and the frontend's public API URL and OIDC client settings.
5. Run `python staging_preflight.py`, verify `alembic current`, and apply any later migrations in a controlled job.
6. Test readiness and end-to-end authenticated tenant isolation and invoice/payment flows.

The Supabase security advisor currently reports informational no-policy notices, expected because direct Data API access is not intended.

## Verified service state, 23 October 2026

- Supabase: `ACTIVE_HEALTHY`; migration `0002_supabase_access`.
- Public Auth JWKS: ES256 / P-256 key available.
- Render: only deployment `dep-dbddmujncjis739rbf3g` is `update_failed`.
  Logs show missing OIDC settings; database connectivity is not yet established.
- Vercel: a successful preview exists for commit `4037c75`; the environment
  variable list is empty. A successful build does not establish API connectivity.
- Backend CI for `4037c75` failed because the Supabase test left cached provider
  configuration behind. Commit `ff3b25d` isolates auth state per test and passes
  all three GitHub workflows; the local backend suite has 46 passing tests.

No production release or paid infrastructure was enabled. Before activating
Supabase mode on a hosted preview, securely configure the backend database,
authentication and CORS, deploy staging, verify readiness, and exercise real
sign-in plus cross-tenant customer/invoice/payment access.
