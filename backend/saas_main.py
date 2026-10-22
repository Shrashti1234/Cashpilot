"""Production SaaS API composition. Legacy demo app remains separate.

Requires SAAS_DATABASE_URL and configured OIDC environment variables.
Apply 'alembic upgrade head' before starting. Never use legacy demo routes.
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
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
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        engine.dispose()
        raise
    app.state.session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield
    finally:
        engine.dispose()


def allowed_origins() -> list[str]:
    """Explicit HTTPS origins, with localhost exceptions for development."""
    raw = os.getenv("CASH_PILOT_CORS_ORIGINS", "")
    origins = [value.strip().rstrip("/") for value in raw.split(",") if value.strip()]
    for origin in origins:
        if "*" in origin or not (origin.startswith("https://") or
                origin.startswith("http://localhost:") or
                origin.startswith("http://127.0.0.1:")):
            raise RuntimeError("CORS origins must be HTTPS or localhost")
        if "/" in origin.split("://", 1)[1]:
            raise RuntimeError("CORS origin must not contain a path")
    return origins


app = FastAPI(title="CashPilot SaaS API", version="1.0.0-alpha", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=allowed_origins(),
    allow_credentials=False, allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
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


@app.get("/ready")
def readiness():
    """Check database connectivity without leaking SQL errors."""
    factory = getattr(app.state, "session_factory", None)
    if factory is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    try:
        with factory() as db:
            db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Service not ready")
    return {"status": "ready", "service": "cashpilot-saas"}
