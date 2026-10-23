# CashPilot SaaS Backend Hosting

The existing Render staging service is live, and both `/health` and `/ready`
return 200. See [the staging configuration](SUPABASE_STAGING.md) and
[the browser/API/database verification report](DEPLOYMENT_VERIFICATION.md).

## Container

Build from the `backend/` directory: `docker build -t cashpilot-saas .`.
The image runs `saas_main:app` on port 8080 as an unprivileged user; it does **not** expose the legacy demo application.

## Deployment prerequisites

1. Provision managed PostgreSQL with TLS, backups and restricted network access.
2. Configure a trusted provider issuing supported RS256 or ES256 access tokens. Deployed staging uses Supabase Auth, the `authenticated` audience and the project JWKS endpoint.
3. Configure secrets using the host's environment manager (see `backend/.env.example` for **placeholders only**). Do not put backend credentials into Vercel `VITE_*` variables.
4. From a controlled migration job using separate administrative database credentials, run `alembic upgrade head`. The restricted runtime login cannot run schema migrations. Do not run migrations concurrently in application containers.
5. Start the container. `GET /health` is liveness; `GET /ready` verifies PostgreSQL connectivity. Restrict the backend's network ingress to HTTPS and trusted proxies.
6. In Vercel preview, configure `VITE_SAAS_API_URL` to the HTTPS backend origin and the public OIDC settings. Register the exact frontend redirect URI with the identity provider.
7. Validate authenticated onboarding, tenant isolation, partial payments, invoice disputes, idempotency and recovery with non-sensitive test data before accepting real customers.

## Security notes

- Never point `VITE_SAAS_API_URL` to the legacy demo server.
- Explicitly set `CASH_PILOT_CORS_ORIGINS` to the frontend origin; wildcard origins are rejected.
- Deploy only to a protected staging environment until authorization tests and audit logging are reviewed.
- The Docker image deliberately does **not** run database migrations on startup.
- A passing container build or `/health` does not establish production readiness.

## Continuous integration

The `SaaS container build` workflow builds the Docker image and verifies the non-root runtime user, correct FastAPI entrypoint and Python compilation. It does **not** prove connectivity to a real OIDC provider or PostgreSQL instance. Deploy to staging only after the host is configured with the required secrets.
