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


def test_invoice_summary_and_payment_history_are_tenant_scoped(api):
    client, identity = api
    base = "/api/v1/organizations/a"
    created = client.post(base + "/invoices", json={
        "customer_id": "ca", "invoice_number": "INV-SUMMARY",
        "due_date": "2020-01-01", "total_paise": 12500})
    assert created.status_code == 201, created.text
    invoice_id = created.json()["id"]
    summary = client.get(base + "/invoices/summary")
    assert summary.status_code == 200, summary.text
    assert summary.json() == {
        "total_invoiced_paise": 12500, "paid_paise": 0,
        "outstanding_paise": 12500, "overdue_paise": 12500,
        "invoice_count": 1}
    payment = client.post(base + f"/invoices/{invoice_id}/payments",
                          json={"amount_paise": 2500, "idempotency_key": "summary-payment"})
    assert payment.status_code == 201
    summary = client.get(base + "/invoices/summary").json()
    assert summary["paid_paise"] == 2500
    assert summary["outstanding_paise"] == 10000
    assert summary["overdue_paise"] == 10000
    history = client.get(base + f"/invoices/{invoice_id}/payments")
    assert history.status_code == 200
    assert len(history.json()["payments"]) == 1
    assert history.json()["payments"][0]["amount_paise"] == 2500
    assert client.get(base + "/invoices/not-found/payments").status_code == 404
    identity["user"] = "bob"
    assert client.get(base + "/invoices/summary").status_code == 403
    assert client.get(base + f"/invoices/{invoice_id}/payments").status_code == 403
    assert client.get("/api/v1/organizations/b/invoices/summary").json()["invoice_count"] == 0


def test_collections_plan_prioritizes_overdue_and_blocks_other_tenants(api):
    client, identity = api
    base = "/api/v1/organizations/a"
    created = client.post(base + "/invoices", json={
        "customer_id": "ca", "invoice_number": "COLLECT-1",
        "due_date": "2020-01-01", "total_paise": 50000})
    assert created.status_code == 201
    invoice_id = created.json()["id"]
    result = client.get(base + "/collections/plan")
    assert result.status_code == 200, result.text
    payload = result.json()
    assert payload["method"] == "explainable_rules_not_ml"
    assert payload["total_outstanding_paise"] == 50000
    assert payload["actions"][0]["invoice_id"] == invoice_id
    assert payload["actions"][0]["action"] == "review_followup"
    identity["user"] = "bob"
    assert client.get(base + "/collections/plan").status_code == 403
    other = client.get("/api/v1/organizations/b/collections/plan")
    assert other.status_code == 200
    assert other.json()["actions"] == []
