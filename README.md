# CashPilot

Financial intelligence for small businesses — **authenticated SaaS staging deployed**.

[Open CashPilot staging](https://cashpilot-git-feature-saas-fo-bbd64b-shrashti-agarwals-projects.vercel.app)
· [Deployment verification](docs/DEPLOYMENT_VERIFICATION.md)
· [Backend readiness](https://cashpilot-saas-staging.onrender.com/ready)

The preview retains Vercel access protection. New accounts require Supabase email
confirmation. The free backend can take time to wake.

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
is provisioned, and hosted sign-in, customer/invoice creation, partial payments,
token refresh and tenant isolation have passed real browser/API/database checks.
The legacy demo remains separate from the SaaS API.

Frontend checks: `cd frontend`, then `npm test` and `npm run build`.
The authentication tests cover sign-in, email confirmation, refresh, expiry,
sign-out and clearing selected businesses when users change. They mock Supabase;
they do not establish a successful hosted deployment.

## Legacy demo limitations
The `main:app` demo is for **local development only** and has no authentication or user isolation. Do not enter real financial data or deploy that app publicly. The anomaly heuristic is not fraud detection, and the UI does not yet display anomaly events. Use the separate SaaS application for authenticated staging work. Production hardening remains pending. No trained ML model or Decision Lab is implemented yet.
