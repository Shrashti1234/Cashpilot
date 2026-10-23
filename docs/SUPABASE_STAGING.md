# CashPilot deployed staging

Verified on 23 October 2026. This is the authenticated SaaS foundation; no trained ML model or Decision Lab is claimed.

| Service | Verified state |
| --- | --- |
| Frontend | https://cashpilot-git-feature-saas-fo-bbd64b-shrashti-agarwals-projects.vercel.app |
| FastAPI | https://cashpilot-saas-staging.onrender.com |
| Liveness / readiness | Both /health and /ready return HTTP 200 |
| Database | Supabase cashpilot-db, PostgreSQL 17, ACTIVE_HEALTHY |
| Schema | Alembic 0003_backend_runtime_role |

Backend deployment `dep-dbdehvqhv4oc73bnf4og` is live at executable commit `1eb16b08ae4099fc96b5c07e8e56b1a889db1524`. The matching Vercel preview is READY. Use the stable branch address above: it is the exact origin allowed by backend CORS. Existing Vercel preview protection is retained.

## Database access

The backend uses the confirmed IPv4 session pooler `aws-0-ap-northeast-2.pooler.supabase.com:5432`. Its dedicated `cashpilot_backend` login has SELECT/INSERT/UPDATE access to the six SaaS tables and read access to alembic_version. It has no superuser, role-creation, database-creation, replication or global RLS-bypass privilege, and a connection limit of 10. It cannot delete business records or run schema migrations.

RLS policies permit only this trusted backend role. FastAPI enforces JWT identity and organization membership. Database access remains revoked for anon and authenticated, and neither is a member of the backend role. The post-deployment security advisor has no findings.

The generated runtime credential is stored in Render's environment settings. The database owner's password was not needed or changed. Rotate the runtime credential administratively and update SAAS_DATABASE_URL; never commit credentials or put them in browser variables.

TLS uses `sslmode=verify-full` and `sslrootcert=/app/certs/supabase-root-2021.crt`. The live pooler connection passed certificate-chain and hostname verification. See [certificate notes](../backend/certs/README.md).

## Authentication and verification

Supabase email/password authentication is configured in the feature branch's Vercel Preview environment. The backend checks its issuer, authenticated audience, ES256 signature and user role. New-account email confirmation remains required.

See [the deployment verification report](DEPLOYMENT_VERIFICATION.md). Temporary test identities, sessions and business records were removed after verification.

## Operational limits

- The existing free Render plan can sleep between requests.
- Backend auto-deploy is off; deploy deliberately after CI succeeds.
- Run migrations administratively, separately from the restricted runtime login.
- No main-branch merge, production promotion or paid infrastructure was enabled.
- Production hardening, backup/restore drills, audit logging, rate limits and trained ML capabilities remain separate work.
