"""API authorization tests use dependency overrides only in isolated tests."""
from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
import pytest

from saas_api import router, get_saas_session, get_verified_identity
from saas_domain import SaaSBase, Organization, Membership, Customer


@pytest.fixture
def api():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=__import__("sqlalchemy").pool.StaticPool)
    @event.listens_for(engine, "connect")
    def fk_on(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")
    SaaSBase.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([Organization(id="a", name="Shop", mode="micro"),
                    Organization(id="b", name="Supplier", mode="b2b")])
        db.flush()
        db.add_all([Membership(organization_id="a", user_id="alice", role="owner"),
                    Membership(organization_id="b", user_id="bob", role="owner"),
                    Customer(id="ca", organization_id="a", name="Buyer")])
        db.commit()
    app = FastAPI()
    app.include_router(router)
    identity = {"user": "alice"}
    def db_override():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_saas_session] = db_override
    app.dependency_overrides[get_verified_identity] = lambda: identity["user"]
    with TestClient(app) as client:
        yield client, identity
    engine.dispose()


def test_router_fails_closed_without_identity():
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        response = client.get("/api/v1/organizations/a/invoices")
        assert response.status_code == 503


def test_invoice_and_partial_payment(api):
    client, identity = api
    path = "/api/v1/organizations/a"
    response = client.post(path + "/invoices", json={
        "customer_id": "ca", "invoice_number": "INV-1",
        "due_date": "2026-11-10", "total_paise": 10000})
    assert response.status_code == 201, response.text
    invoice_id = response.json()["id"]
    assert len(client.get(path + "/invoices").json()["invoices"]) == 1
    payment = client.post(path + f"/invoices/{invoice_id}/payments",
                          json={"amount_paise": 4000, "idempotency_key": "unique-1"})
    assert payment.status_code == 201, payment.text
    duplicate = client.post(path + f"/invoices/{invoice_id}/payments",
                            json={"amount_paise": 4000, "idempotency_key": "unique-1"})
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == payment.json()["id"]
    overpay = client.post(path + f"/invoices/{invoice_id}/payments",
                          json={"amount_paise": 7000, "idempotency_key": "unique-2"})
    assert overpay.status_code == 422
    identity["user"] = "bob"
    assert client.get(path + "/invoices").status_code == 403
    assert client.post(path + "/customers", json={"name": "Other"}).status_code == 403


def test_customer_list_is_tenant_scoped(api):
    client, identity = api
    own = client.get("/api/v1/organizations/a/customers")
    assert own.status_code == 200
    assert own.json() == {"customers": [{"id": "ca", "name": "Buyer"}]}
    created = client.post("/api/v1/organizations/a/customers", json={"name": "  New Client  "})
    assert created.status_code == 201
    names = {customer["name"] for customer in client.get(
        "/api/v1/organizations/a/customers").json()["customers"]}
    assert names == {"Buyer", "New Client"}
    assert client.get("/api/v1/organizations/b/customers").status_code == 403
    identity["user"] = "bob"
    assert client.get("/api/v1/organizations/a/customers").status_code == 403
    assert client.get("/api/v1/organizations/b/customers").json() == {"customers": []}
