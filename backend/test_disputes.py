from datetime import date
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from saas_domain import SaaSBase, Organization, Membership, Customer, create_invoice, TenantAccessDenied
from disputes import open_dispute, change_dispute_status, list_disputes


@pytest.fixture
def setup():
    engine = create_engine("sqlite:///:memory:")
    @event.listens_for(engine, "connect")
    def fk_on(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")
    SaaSBase.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([Organization(id="a", name="A", mode="micro"),
                    Organization(id="b", name="B", mode="b2b")])
        db.flush()
        db.add_all([Membership(organization_id="a", user_id="alice", role="owner"),
                    Membership(organization_id="b", user_id="bob", role="owner"),
                    Membership(organization_id="a", user_id="viewer", role="viewer"),
                    Customer(id="ca", organization_id="a", name="Buyer")])
        db.flush()
        invoice = create_invoice(db, user_id="alice", organization_id="a", customer_id="ca",
                                 invoice_number="INV-1", due_date=date(2026, 11, 1), total_paise=10000)
        db.commit()
        yield db, invoice.id
    engine.dispose()


def test_dispute_lifecycle(setup):
    db, invoice_id = setup
    d = open_dispute(db, user_id="alice", organization_id="a", invoice_id=invoice_id,
                     reason="delivery", description="Delivery confirmation pending")
    assert d.status == "open"
    with pytest.raises(ValueError):
        change_dispute_status(db, user_id="alice", organization_id="a",
                              dispute_id=d.id, status="resolved", resolution_note="Done")
    change_dispute_status(db, user_id="alice", organization_id="a", dispute_id=d.id,
                          status="under_review")
    with pytest.raises(ValueError):
        change_dispute_status(db, user_id="alice", organization_id="a",
                              dispute_id=d.id, status="resolved")
    change_dispute_status(db, user_id="alice", organization_id="a",
                          dispute_id=d.id, status="resolved", resolution_note="Confirmed")
    assert d.resolved_at is not None
    assert len(list_disputes(db, user_id="alice", organization_id="a")) == 1


def test_cross_tenant_and_viewer_denied(setup):
    db, invoice_id = setup
    with pytest.raises(TenantAccessDenied):
        open_dispute(db, user_id="bob", organization_id="a", invoice_id=invoice_id,
                     reason="other", description="Not allowed")
    with pytest.raises(TenantAccessDenied):
        open_dispute(db, user_id="viewer", organization_id="a", invoice_id=invoice_id,
                     reason="other", description="Not allowed")
    with pytest.raises(ValueError):
        open_dispute(db, user_id="bob", organization_id="b", invoice_id=invoice_id,
                     reason="other", description="Not found")
