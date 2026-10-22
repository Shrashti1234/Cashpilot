# CashPilot

Real-time cash-flow dashboard for small businesses. Milestone 1 is a local demo, not production-ready.

## Run locally

Backend:
```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Frontend (separate terminal):
```bash
cd frontend
npm install
npm run dev
```

Visit http://localhost:5173 and open two tabs to verify WebSocket synchronization. API documentation: http://localhost:8000/docs.

## Current functionality
- Add income and expense transactions
- Live balance, income, expense totals
- Interactive cash-flow chart
- Search and filter transaction history
- WebSocket updates across connected tabs

## Limitations
Transactions are stored in memory and disappear after backend restart. No authentication, tenant isolation, persistent database, ML, or production-safe event broadcasting yet. Use synthetic data only and do not deploy this version publicly. Next: PostgreSQL, authentication, anomaly detection, forecasting, CSV import, tests, deployment.
