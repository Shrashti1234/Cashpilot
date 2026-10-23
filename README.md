# CashPilot

Real-time financial intelligence workspace — **local demo MVP v0.2**.

## Implemented
- Responsive React + TypeScript dashboard with Recharts
- Transaction creation, search, filters and WebSocket events
- Persistent transaction storage using SQLAlchemy (SQLite by default, PostgreSQL via DATABASE_URL)
- Category-median expense anomaly flag in API responses and WebSocket events (simple heuristic, **not** trained ML)
- Backend API and WebSocket tests

## Run locally

Backend:
```bash
cd backend
python -m venv .venv
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Frontend (second terminal; Node.js 24):
```bash
cd frontend
npm ci
npm run dev
```

Visit http://localhost:5173 and API docs at http://localhost:8000/docs. Add a transaction and refresh to verify SQLite persistence. Open two tabs to verify WebSocket updates.

Tests: `cd backend && python -m pytest -q`

## Authenticated SaaS workspace

The separate `backend/saas_main.py` application provides organizations,
tenant-scoped customers, invoices, partial payments, disputes and collections
rules. It verifies signed access tokens and business membership. The React app
supports generic OIDC or a dedicated Supabase email/password flow with token
refresh and in-memory sessions.

Use [the authentication setup guide](docs/OIDC_SETUP.md) and
[the staging status and checklist](docs/SUPABASE_STAGING.md). The Supabase schema
is provisioned, but hosted backend readiness and real-user end-to-end login are
still pending. The legacy demo below remains separate from the SaaS API.

Frontend checks: `cd frontend`, then `npm test` and `npm run build`.
The authentication tests cover sign-in, email confirmation, refresh, expiry,
sign-out and clearing selected businesses when users change. They mock Supabase;
they do not establish a successful hosted deployment.

## Important limitations
**Local development only.** No authentication, user isolation, production event bus, or production-ready security. Do not enter real financial data or deploy publicly. The anomaly heuristic is not fraud detection. The UI does not yet display anomaly events. PostgreSQL needs a compatible driver and configured URL. Next: auth + multi-tenant DB design, anomaly panel, forecast, CSV import, deployment and CI.
