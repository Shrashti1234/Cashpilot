from datetime import date
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from saas_domain import (
    SaaSBase, Organization, Membership, Customer, TenantAccessDenied,
    create_invoice, list_invoices, record_payment,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    @event.listens_for(engine, "connect")
    def fk_on(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    SaaSBase.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([
            Organization(id="a", name="Micro Shop", mode="micro"),
            Organization(id="b", name="Supplier", mode="b2b"),
            Membership(organization_id="a", user_id="alice", role="owner"),
            Membership(organization_id="b", user_id="bob", role="owner"),
            Membership(organization_id="a", user_id="viewer", role="viewer"),
            Customer(id="ca", organization_id="a", name="A Customer"),
            Customer(id="cb", organization_id="b", name="B Customer"),
        ])
        session.commit()
        yield session
    engine.dispose()


def test_cannot_read_another_tenant(db):
    create_invoice(db, user_id="alice", organization_id="a", customer_id="ca",
                   invoice_number="INV-1", due_date=date(2026, 11, 1), total_paise=10000)
    assert len(list_invoices(db, user_id="alice", organization_id="a")) == 1
    with pytest.raises(TenantAccessDenied):
        list_invoices(db, user_id="alice", organization_id="b")
    assert list_invoices(db, user_id="bob", organization_id="b") == []


def test_cross_tenant_customer_rejected(db):
    with pytest.raises(ValueError):
        create_invoice(db, user_id="alice", organization_id="a", customer_id="cb",
                       invoice_number="INV-2", due_date=date(2026, 11, 1), total_paise=100)


def test_viewer_cannot_write(db):
    with pytest.raises(TenantAccessDenied):
        create_invoice(db, user_id="viewer", organization_id="a", customer_id="ca",
                       invoice_number="INV-3", due_date=date(2026, 11, 1), total_paise=100)


def test_partial_payments_and_idempotency(db):
    invoice = create_invoice(db, user_id="alice", organization_id="a", customer_id="ca",
                             invoice_number="INV-4", due_date=date(2026, 11, 1), total_paise=10000)
    p = record_payment(db, user_id="alice", organization_id="a", invoice_id=invoice.id,
                       amount_paise=4000, idempotency_key="payment-1")
    assert record_payment(db, user_id="alice", organization_id="a", invoice_id=invoice.id,
                          amount_paise=4000, idempotency_key="payment-1").id == p.id
    with pytest.raises(ValueError):
        record_payment(db, user_id="alice", organization_id="a", invoice_id=invoice.id,
                       amount_paise=7000, idempotency_key="payment-2")
    with pytest.raises(TenantAccessDenied):
        record_payment(db, user_id="bob", organization_id="a", invoice_id=invoice.id,
                       amount_paise=100, idempotency_key="payment-3")
