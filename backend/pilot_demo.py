"""Loopback-only disposable practice workspace. Never use as the hosted API."""
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, event
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session
from starlette.middleware.trustedhost import TrustedHostMiddleware

from auth_identity import get_verified_identity
from banking_api import router as banking
from collection_worklist_api import router as collections
from dashboard_api import router as dashboard
from receivable_import_api import router as imports
from saas_api import get_saas_session, router as invoices
from saas_domain import Membership, Organization, SaaSBase

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


if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=18081, proxy_headers=False)
