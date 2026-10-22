"""CashPilot local-development API. Do not expose publicly without authentication."""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, String, DateTime, select, func
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./cashpilot.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

class Base(DeclarativeBase):
    pass

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(String(36), primary_key=True)
    title = Column(String(100), nullable=False)
    amount = Column(String(32), nullable=False)
    kind = Column(String(7), nullable=False)
    category = Column(String(40), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(title="CashPilot API", version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
clients: set[WebSocket] = set()
sequence = 0

class TransactionIn(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    kind: str = Field(pattern="^(income|expense)$")
    category: str = Field(min_length=1, max_length=40)

def serialize(t: Transaction):
    return {"id": t.id, "title": t.title, "amount": t.amount, "kind": t.kind, "category": t.category, "created_at": t.created_at.isoformat() + ("Z" if t.created_at.tzinfo is None else "")}

def summary(rows):
    income = sum((Decimal(t.amount) for t in rows if t.kind == "income"), Decimal("0"))
    expenses = sum((Decimal(t.amount) for t in rows if t.kind == "expense"), Decimal("0"))
    return {"income": str(income), "expenses": str(expenses), "balance": str(income - expenses), "count": len(rows)}

def anomaly_for(new: Transaction, history):
    """Transparent statistical flag; not a trained fraud or accounting model."""
    peers = [float(Decimal(t.amount)) for t in history if t.kind == "expense" and t.category == new.category]
    if new.kind != "expense" or len(peers) < 5:
        return {"flagged": False, "reason": "Insufficient comparable expenses"}
    peers.sort()
    median = peers[len(peers)//2] if len(peers)%2 else (peers[len(peers)//2-1]+peers[len(peers)//2])/2
    flagged = float(Decimal(new.amount)) > max(3 * median, median + 1000)
    return {"flagged": flagged, "reason": "Expense exceeds 3x category median and median + 1000 INR" if flagged else "Within simple category threshold", "category_median": round(median,2)}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/transactions")
def list_transactions():
    with SessionLocal() as db:
        rows = db.scalars(select(Transaction).order_by(Transaction.created_at.desc())).all()
        return {"transactions": [serialize(t) for t in rows], "summary": summary(rows), "sequence": sequence}

@app.post("/transactions", status_code=201)
async def add_transaction(data: TransactionIn):
    global sequence
    if not data.title.strip() or not data.category.strip():
        raise HTTPException(status_code=422, detail="Title and category cannot be blank")
    with SessionLocal() as db:
        history = db.scalars(select(Transaction)).all()
        tx = Transaction(id=str(uuid4()), title=data.title.strip(), amount=str(data.amount), kind=data.kind, category=data.category.strip(), created_at=datetime.now(timezone.utc))
        anomaly = anomaly_for(tx, history)
        db.add(tx)
        db.commit()
        result = serialize(tx)
        all_rows = db.scalars(select(Transaction)).all()
        totals = summary(all_rows)
    sequence += 1
    event = {"type": "transaction.created", "sequence": sequence, "transaction": result, "summary": totals, "anomaly": anomaly}
    for ws in list(clients):
        try:
            await ws.send_json(event)
        except Exception:
            clients.discard(ws)
    return {**result, "anomaly": anomaly}

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    # Local demo only: no authentication or tenant isolation.
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
