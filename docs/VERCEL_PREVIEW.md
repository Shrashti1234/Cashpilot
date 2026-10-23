# CashPilot Vercel Preview Setup

The existing preview is configured and verified. Open the stable feature-branch
address in [the staging guide](SUPABASE_STAGING.md). Vercel's existing access
protection remains enabled. See [the live verification report](DEPLOYMENT_VERIFICATION.md).

The repository contains **two separate applications**:

- `frontend/` — React/Vite SPA suitable for a Vercel preview.
- `backend/saas_main.py` — Python/FastAPI authenticated SaaS API, requiring a separate PostgreSQL-backed runtime.

## Create a preview project (not production)

1. In Vercel, import GitHub repository `Shrashti1234/Cashpilot`.
2. Set **Root Directory** to `frontend`.
3. Set Framework Preset to **Vite**, Build Command `npm run build`, Output Directory `dist`.
4. Deploy branch `feature/saas-foundation` as **Preview**. Do not promote to production until the checklist below passes.
5. Without `VITE_SAAS_API_URL`, this runs the legacy **demo UI** only. Demo mode must not receive real financial/customer data. The localhost demo backend is not hosted by Vercel.
6. For the deployed Supabase flow, set `VITE_AUTH_PROVIDER=supabase`, `VITE_SAAS_API_URL`, `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY`, scoped to the feature branch in **Preview**. Generic OIDC instead uses the `VITE_OIDC_*` settings in the authentication guide. Never put a client secret, database URL or access token in Vite variables.
7. Register the exact Vercel preview callback origin with the identity provider. Configure the backend `CASH_PILOT_CORS_ORIGINS` to allow the exact frontend origin, and configure backend JWT issuer/audience/JWKS as described in `docs/OIDC_SETUP.md`.

## Release blockers

- Supabase Auth, the separate HTTPS backend, PostgreSQL and migrations are deployed; backup/restore procedures still need production review.
- Production domains, explicit CORS origins, logging, rate limits and audit trail must be reviewed.
- Hosted tenant isolation and payment safety checks pass; broader recovery procedures remain pending.
- Confirm GitHub CI passes for the exact commit before promoting anything.
- Do not expose the legacy demo API or store actual customer financial data in demo mode.

The `frontend/vercel.json` file provides SPA fallback routing and basic response headers. It is **not** a substitute for a security review.
