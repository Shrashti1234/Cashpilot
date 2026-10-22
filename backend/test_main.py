import os
import tempfile

# Must configure DB before importing application module.
_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = "sqlite:///" + _db.name

from fastapi.testclient import TestClient
from main import app

def test_transaction_persists_and_updates_totals():
    with TestClient(app) as client:
        response = client.post("/transactions", json={"title": "Sample sale", "amount": "1250.50", "kind": "income", "category": "Sales"})
        assert response.status_code == 201, response.text
        payload = client.get("/transactions").json()
        assert payload["summary"]["income"] == "1250.50"
        assert payload["summary"]["count"] >= 1
        assert any(t["title"] == "Sample sale" for t in payload["transactions"])

def test_invalid_amount_rejected():
    with TestClient(app) as client:
        response = client.post("/transactions", json={"title": "Invalid", "amount": -2, "kind": "expense", "category": "Other"})
        assert response.status_code == 422

def test_websocket_event():
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            assert ws.receive_json()["type"] == "connected"
            response = client.post("/transactions", json={"title": "Office supplies", "amount": "50", "kind": "expense", "category": "Office"})
            assert response.status_code == 201
            event = ws.receive_json()
            assert event["type"] == "transaction.created"
            assert event["transaction"]["title"] == "Office supplies"
