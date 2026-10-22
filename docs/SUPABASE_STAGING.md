# CashPilot Supabase staging

Project: `cashpilot-db` (`gdjgmgfuzpqcedqgdozv`). PostgreSQL 17 is active.

The six `saas_*` tables match the initial Alembic migration `0001_saas_foundation`. RLS is enabled on the SaaS tables and `alembic_version`. No browser-facing policies are installed because the FastAPI server enforces tenant authorization.

## Remaining deployment steps

1. Deploy the existing FastAPI Docker backend to a staging HTTPS host.
2. Set `SAAS_DATABASE_URL` in the backend host's secret manager using the Supabase Connect panel. Never commit or share database passwords.
3. Configure an OIDC provider that issues access tokens compatible with the existing RS256/JWKS verification. Database provisioning does not automatically configure OIDC.
4. Configure the backend CORS allowlist and the frontend's public API URL and OIDC client settings.
5. Run `python staging_preflight.py`, verify `alembic current`, and apply any later migrations in a controlled job.
6. Test readiness and end-to-end authenticated tenant isolation and invoice/payment flows.

The Supabase security advisor currently reports informational no-policy notices, expected because direct Data API access is not intended.
