"""Production SaaS API composition. Legacy demo app remains separate.

Requires SAAS_DATABASE_URL and configured OIDC environment variables.
Apply 'alembic upgrade head' before starting. Never use legacy demo routes.
"""
import os
from urllib.parse import urlsplit
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from auth_identity import _provider_config
from organizations_api import router as organizations_router
from saas_api import get_saas_session, router as invoices_router
from intelligence_api import router as intelligence_router
from disputes_api import router as disputes_router
from operations_api import router as operations_router
from finance_api import router as finance_router
from recurring_api import router as recurring_router
from teams_api import router as teams_router
from dashboard_api import router as dashboard_router
from buyer_api import router as buyer_router
from banking_api import router as banking_router
from contacts_api import router as contacts_router
from forecast_journal_api import router as forecast_journal_router
from evidence_api import router as evidence_router
from api_security import safe_validation_error


@asynccontextmanager
async def lifespan(app: FastAPI):
    _provider_config()  # Fail startup if trusted identity provider is absent.
    database_url = os.getenv("SAAS_DATABASE_URL", "")
    if not database_url.startswith("postgresql+psycopg://"):
        raise RuntimeError("SAAS_DATABASE_URL must use PostgreSQL psycopg")
    engine = create_engine(database_url, pool_pre_ping=True, hide_parameters=True)
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
    """Require exact browser origins; reject credentials, paths and wildcards."""
    raw = os.getenv("CASH_PILOT_CORS_ORIGINS", "")
    origins = [value.strip() for value in raw.split(",") if value.strip()]
    for origin in origins:
        parsed = urlsplit(origin)
        try:
            port = parsed.port
        except ValueError:
            raise RuntimeError("CORS origin has invalid port") from None
        localhost = parsed.hostname in ("localhost", "127.0.0.1")
        scheme_ok = parsed.scheme == "https" or (localhost and parsed.scheme == "http")
        if (not scheme_ok or not parsed.hostname or parsed.username or parsed.password
                or parsed.path or parsed.query or parsed.fragment or "*" in origin
                or port is not None and not (1 <= port <= 65535)):
            raise RuntimeError("CORS origins must be exact HTTPS origins or local development origins")
    return origins


app = FastAPI(title="CashPilot SaaS API", version="1.0.0-alpha", lifespan=lifespan)
app.add_exception_handler(RequestValidationError,safe_validation_error)


@app.middleware('http')
async def private_api_headers(request,call_next):
    response=await call_next(request)
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
    return response
app.add_middleware(
    CORSMiddleware, allow_origins=allowed_origins(),
    allow_credentials=False, allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(organizations_router)
app.include_router(invoices_router)
app.include_router(intelligence_router)
app.include_router(disputes_router)
app.include_router(operations_router)
app.include_router(finance_router)
app.include_router(recurring_router)
app.include_router(teams_router)
app.include_router(dashboard_router)
app.include_router(buyer_router)
app.include_router(banking_router)
app.include_router(contacts_router)
app.include_router(forecast_journal_router)
app.include_router(evidence_router)


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
