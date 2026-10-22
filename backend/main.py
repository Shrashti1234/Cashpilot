from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title="CashPilot API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])
transactions = []
clients: set[WebSocket] = set()
sequence = 0

class TransactionIn(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    kind: str = Field(pattern="^(income|expense)$")
    category: str = Field(min_length=1, max_length=40)

def snapshot():
    income = sum(Decimal(t["amount"]) for t in transactions if t["kind"] == "income")
    expenses = sum(Decimal(t["amount"]) for t in transactions if t["kind"] == "expense")
    return {"income": str(income), "expenses": str(expenses), "balance": str(income - expenses), "count": len(transactions)}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/transactions")
def list_transactions():
    return {"transactions": transactions, "summary": snapshot(), "sequence": sequence}

@app.post("/transactions", status_code=201)
async def add_transaction(data: TransactionIn):
    global sequence
    transaction = {
        "id": str(uuid4()), "title": data.title.strip(), "amount": str(data.amount),
        "kind": data.kind, "category": data.category.strip(),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    transactions.insert(0, transaction)
    sequence += 1
    event = {"type": "transaction.created", "sequence": sequence, "transaction": transaction, "summary": snapshot()}
    stale = []
    for client in list(clients):
        try:
            await client.send_json(event)
        except Exception:
            stale.append(client)
    for client in stale:
        clients.discard(client)
    return transaction

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    try:
        await ws.send_json({"type": "connected", "sequence": sequence})
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(ws)
