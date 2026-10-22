"""Production SaaS API composition. Legacy demo app remains separate.

Requires SAAS_DATABASE_URL and configured OIDC environment variables.
Apply 'alembic upgrade head' before starting. Never use legacy demo routes.
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from auth_identity import _provider_config
from organizations_api import router as organizations_router
from saas_api import get_saas_session, router as invoices_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    _provider_config()  # Fail startup if trusted identity provider is absent.
    database_url = os.getenv("SAAS_DATABASE_URL", "")
    if not database_url.startswith("postgresql+psycopg://"):
        raise RuntimeError("SAAS_DATABASE_URL must use PostgreSQL psycopg")
    engine = create_engine(database_url, pool_pre_ping=True)
    app.state.session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield
    finally:
        engine.dispose()


app = FastAPI(title="CashPilot SaaS API", version="1.0.0-alpha", lifespan=lifespan)
app.include_router(organizations_router)
app.include_router(invoices_router)


def session_dependency():
    factory = app.state.session_factory
    with factory() as db:
        yield db


app.dependency_overrides[get_saas_session] = session_dependency


@app.get("/health")
def health():
    return {"status": "ok", "service": "cashpilot-saas"}
