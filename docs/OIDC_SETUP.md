# Secure SaaS authentication setup

CashPilot keeps the legacy demo separate from the authenticated SaaS experience.

## Supabase Auth (staging integration)

Supabase uses its own browser authentication SDK. Do not point the generic OIDC
PKCE client at the Supabase project URL. Select the dedicated Supabase flow with:

```dotenv
VITE_AUTH_PROVIDER=supabase
VITE_SAAS_API_URL=https://cashpilot-saas-staging.onrender.com
VITE_SUPABASE_URL=https://gdjgmgfuzpqcedqgdozv.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=<modern publishable key from Project Settings>
```

These are public build settings. The client accepts modern `sb_publishable_`
keys only. Never use a service-role key, secret key, database URL or password.
The browser uses Supabase only for authentication; all business data continues
through the tenant-authorized FastAPI routes.

The flow supports email/password sign-in, account creation (with an email
confirmation message when required), and local-session sign-out. Confirm email
using Supabase's configured confirmation destination, then return to CashPilot
and sign in. No OAuth or recovery callback flow is implemented here.

Sessions stay in memory (`persistSession: false`); a reload requires signing in
again. The SDK refreshes tokens while the page is open. Auth state changes pass
the refreshed access token to API consumers. Expiry without a successful refresh
removes the workspace UI; a different user starts with no selected business.
The backend remains responsible for verifying every token and membership.

Backend settings for this project:

```dotenv
CASH_PILOT_OIDC_ISSUER=https://gdjgmgfuzpqcedqgdozv.supabase.co/auth/v1
CASH_PILOT_OIDC_AUDIENCE=authenticated
CASH_PILOT_OIDC_JWKS_URL=https://gdjgmgfuzpqcedqgdozv.supabase.co/auth/v1/.well-known/jwks.json
```

On 23 October 2026 the public JWKS returned an ES256 P-256 signing key, which
the backend supports. The JWT `role` must also be `authenticated`. This key
inspection and unit tests do not prove a live user can complete the hosted flow.
Render still needs `SAAS_DATABASE_URL` configured securely, the settings above,
and an exact frontend CORS allowlist before deploying and checking `/ready`.

References: [password sign-in](https://supabase.com/docs/reference/javascript/auth-signinwithpassword),
[auth state events](https://supabase.com/docs/reference/javascript/auth-onauthstatechange),
[local sign-out](https://supabase.com/docs/reference/javascript/auth-signout).

## Configure an OIDC provider

For another provider, set `VITE_AUTH_PROVIDER=oidc` (the default).
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
- The generic OIDC flow has no token refresh: expired sessions require signing in again. Supabase refreshes in-memory sessions as described above.
- A fresh page reload drops the in-memory token, so users sign in again; this avoids persistent browser token storage.
- Frontend integration and API tests do not replace a full provider-backed browser E2E security test.
- Add rate limiting, audit logs, monitoring, backup/restore, and production database migration verification before launch.
