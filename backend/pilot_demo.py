"""Loopback-only disposable practice workspace. Never use as the hosted API."""
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session
from starlette.middleware.trustedhost import TrustedHostMiddleware

from auth_identity import get_verified_identity
from banking import BankMatch, BankTransaction
from banking_api import router as banking
from collection_tasks import CollectionTask
from collection_worklist_api import router as collections
from dashboard_api import router as dashboard
from receivable_import_api import router as imports
from saas_api import get_saas_session, router as invoices
from saas_domain import Invoice, Membership, Organization, Payment, SaaSBase, invoice_positions

# Register every table referenced by the shared domain metadata.
import saas_main  # noqa: F401

DEMO_TOKEN = 'cashpilot-disposable-demo'
WORKSPACE_ID = 'local-practice'
ACTOR_ID = 'practice-owner'


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Separate connections let the invoice screen issue concurrent reads safely.
    temp = TemporaryDirectory(prefix='cashpilot-practice-')
    engine = create_engine(URL.create('sqlite', database=str(Path(temp.name) / 'practice.db')))

    @event.listens_for(engine, 'connect')
    def enable_foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')

    try:
        SaaSBase.metadata.create_all(engine)
        app.state.engine = engine
        with Session(engine) as db:
            db.add(Organization(id=WORKSPACE_ID, name='CashPilot practice', mode='b2b'))
            db.flush()
            db.add(Membership(organization_id=WORKSPACE_ID, user_id=ACTOR_ID, role='owner'))
            db.commit()
        yield
    finally:
        engine.dispose()
        temp.cleanup()


app = FastAPI(title='CashPilot disposable local practice API', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=['http://127.0.0.1:5179'], allow_methods=['GET', 'POST'], allow_headers=['Authorization', 'Content-Type'])
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1'])
for router in (banking, collections, dashboard, imports, invoices):
    app.include_router(router)


def demo_identity(authorization: str = Header(default='')):
    if authorization != 'Bearer ' + DEMO_TOKEN:
        raise HTTPException(401, 'Open the local practice page.')
    return ACTOR_ID


def demo_session():
    with Session(app.state.engine) as db:
        yield db


app.dependency_overrides[get_verified_identity] = demo_identity
app.dependency_overrides[get_saas_session] = demo_session


@app.get('/practice/status', dependencies=[Depends(demo_identity)])
def practice_status(response: Response, db: Session = Depends(demo_session)):
    response.headers['Cache-Control'] = 'no-store'
    invoice = db.scalar(select(Invoice).where(Invoice.organization_id == WORKSPACE_ID,
                                              Invoice.invoice_number == 'PILOT-100', Invoice.opening_receivable.is_(True)))
    if not invoice:
        return {'imported': False, 'follow_up': False, 'outstanding_paise': None,
                'received_paise': 0, 'matched_paise': 0}
    invoice_id = invoice.id
    position = invoice_positions(db, WORKSPACE_ID, [invoice])[invoice_id]
    matched = db.scalar(select(func.coalesce(func.sum(Payment.amount_paise), 0))
                        .join(BankMatch, (BankMatch.organization_id == Payment.organization_id) & (BankMatch.payment_id == Payment.id))
                        .join(BankTransaction, (BankTransaction.organization_id == BankMatch.organization_id) & (BankTransaction.id == BankMatch.transaction_id))
                        .where(Payment.organization_id == WORKSPACE_ID, Payment.invoice_id == invoice_id,
                               BankMatch.active.is_(True), BankTransaction.reference == 'PILOT-BANK-1'))
    return {'imported': True, 'follow_up': db.get(CollectionTask, (WORKSPACE_ID, invoice_id)) is not None,
            'outstanding_paise': position['outstanding_paise'], 'received_paise': position['gross_paid_paise'],
            'matched_paise': matched}


if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=18081, proxy_headers=False)
