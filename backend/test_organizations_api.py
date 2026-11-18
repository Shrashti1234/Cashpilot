from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from auth_identity import get_verified_identity
from saas_api import get_saas_session
from organizations_api import router
from saas_domain import SaaSBase


def test_onboarding_creates_owner_and_lists_only_own_organizations():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def fk_on(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")
    SaaSBase.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(router)
    current = {"user": "alice"}
    app.dependency_overrides[get_verified_identity] = lambda: current["user"]
    def db_session():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_saas_session] = db_session
    with TestClient(app) as client:
        assert client.post("/api/v1/organizations", json={"name": "  Shop  ", "mode": "micro"}).status_code == 201
        response = client.get("/api/v1/organizations").json()["organizations"]
        assert len(response) == 1
        assert response[0]["name"] == "Shop"
        assert response[0]["role"] == "owner"
        assert client.post("/api/v1/organizations", json={"name": "Bad", "mode": "enterprise"}).status_code == 422
        current["user"] = "bob"
        assert client.get("/api/v1/organizations").json()["organizations"] == []
    engine.dispose()


def test_onboarding_fails_closed_without_provider():
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        assert client.get("/api/v1/organizations").status_code == 503
