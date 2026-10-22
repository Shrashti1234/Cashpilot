# Secure SaaS authentication setup

CashPilot keeps the legacy demo separate from the authenticated SaaS experience.

## Configure an OIDC provider

Use a trusted provider supporting Authorization Code + PKCE for a **public SPA client**.
Register the exact HTTPS production origin and callback URL, plus localhost callback for development.
Configure a resource-server access token signed with RS256, with audience matching the backend.
An ID token is **not** an API access token.

Frontend Vite build variables (public configuration, **never secrets**):

- `VITE_SAAS_API_URL`: SaaS backend origin.
- `VITE_OIDC_ISSUER`: HTTPS provider authority.
- `VITE_OIDC_CLIENT_ID`: public SPA client ID.
- `VITE_OIDC_SCOPE`: e.g. `openid profile <provider-api-scope>`.

Backend runtime environment:

- `SAAS_DATABASE_URL=postgresql+psycopg://...`
- `CASH_PILOT_OIDC_ISSUER`: exactly the provider token issuer.
- `CASH_PILOT_OIDC_AUDIENCE`: expected API access token audience.
- `CASH_PILOT_OIDC_JWKS_URL`: HTTPS signing-key endpoint.
- `CASH_PILOT_CORS_ORIGINS`: comma-separated allowed frontend origins, e.g. `https://app.example.com,http://localhost:5173`. No wildcard or paths.

Run Alembic migrations before starting `uvicorn saas_main:app` from the backend directory.
Do not use the unauthenticated legacy demo routes for real customer or financial data.

## Current limitations / launch blockers

- A real provider, production HTTPS domain, allowed redirect URIs and API audience are **not yet configured**.
- Configure the newly implemented `CASH_PILOT_CORS_ORIGINS` allowlist for the actual deployed frontend domain.
- No token refresh is configured: expired sessions require signing in again.
- A fresh page reload drops the in-memory token, so users sign in again; this avoids persistent browser token storage.
- Frontend integration and API tests do not replace a full provider-backed browser E2E security test.
- Add rate limiting, audit logs, monitoring, backup/restore, and production database migration verification before launch.
