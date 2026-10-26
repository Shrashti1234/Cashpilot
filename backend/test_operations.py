from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from auth_identity import get_verified_identity
from operations import StockMovement, TradeDocument, calculate_lines
from operations_api import router
from saas_api import get_saas_session, router as invoice_router
from saas_domain import SaaSBase, Organization, Membership, Customer, Invoice


@pytest.fixture
def api():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
    SaaSBase.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([Organization(id='a', name='A', mode='b2b'), Organization(id='b', name='B', mode='b2b')])
        db.flush()
        db.add_all([Membership(organization_id='a', user_id='alice', role='owner'),
                    Membership(organization_id='a', user_id='approver', role='admin'),
                    Membership(organization_id='a', user_id='viewer', role='viewer'),
                    Membership(organization_id='b', user_id='bob', role='owner'),
                    Customer(id='ca', organization_id='a', name='Buyer'), Customer(id='cb', organization_id='b', name='Other')])
        db.commit()
    app = FastAPI()
    app.include_router(router)
    app.include_router(invoice_router)
    who = {'id': 'alice'}
    app.dependency_overrides[get_verified_identity] = lambda: who['id']
    def session():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_saas_session] = session
    with TestClient(app) as c:
        yield c, who, engine
    engine.dispose()


BASE = '/api/v1/organizations/a/operations'
PROFILE = {'legal_name': 'Example Supplier', 'address': 'Test address', 'gstin': '27ABCDE1234F1Z5', 'state_code': '27', 'require_approval': False}
PRODUCT = {'sku': 'SKU-1', 'name': 'Widget', 'unit': 'NOS', 'hsn_sac': '8471', 'unit_price_paise': 10000,
           'tax_rate_bps': 1800, 'track_stock': True, 'reorder_milliunits': 1000}


def setup(c):
    assert c.post(BASE + '/profile', json=PROFILE).status_code == 200
    r = c.post(BASE + '/products', json=PRODUCT)
    assert r.status_code == 201, r.text
    return r.json()['id']


def draft(c, product, kind='invoice', number='INV-1', quantity=2000):
    body = {'kind': kind, 'number': number, 'customer_id': 'ca' if kind != 'purchase_order' else None,
            'issue_date': str(date.today()), 'due_date': str(date.today()),
            'party': {'name': 'Buyer', 'address': 'Recipient address', 'state_code': '27', 'gstin': '', 'place_of_supply': '27'},
            'lines': [{'product_id': product, 'description': 'Widget', 'hsn_sac': '8471', 'unit': 'NOS',
                       'quantity_milliunits': quantity, 'unit_price_paise': 10000, 'discount_paise': 0,
                       'tax_rate_bps': 1800, 'cess_rate_bps': 0}]}
    response = c.post(BASE + '/documents', json=body)
    assert response.status_code == 201, response.text
    return response.json(), body


def test_line_taxes_discount_fractional_quantity_and_conservation():
    line = {'quantity_milliunits': 1500, 'unit_price_paise': 10000, 'discount_paise': 1000, 'tax_rate_bps': 1800, 'cess_rate_bps': 100}
    lines, intra = calculate_lines([line], '27', '27')
    _, inter = calculate_lines([line], '27', '29')
    assert intra['taxable_paise'] == 14000
    assert intra['cgst_paise'] == intra['state_tax_paise'] == 1260
    assert intra['igst_paise'] == 0 and inter['igst_paise'] == 2520
    assert intra['total_paise'] == inter['total_paise'] == 16660
    assert lines[0]['total_paise'] == intra['total_paise']
    with pytest.raises(ValueError):
        calculate_lines([{**line, 'discount_paise': 16000}], '27', '29')


def test_stock_replay_and_invoice_posting_are_atomic(api):
    c, _, engine = api
    product = setup(c)
    doc, _ = draft(c, product)
    path = BASE + '/documents/' + doc['id'] + '/issue'
    assert c.post(path, json={'tax_reviewed': True}).status_code == 422
    with Session(engine) as db:
        assert list(db.scalars(select(Invoice))) == []
        assert db.get(TradeDocument, doc['id']).status == 'draft'
    movement = {'product_id': product, 'quantity_milliunits': 5000, 'reference': 'Counted opening stock', 'request_key': 'count-1'}
    first = c.post(BASE + '/stock', json=movement)
    replay = c.post(BASE + '/stock', json=movement)
    assert first.json()['id'] == replay.json()['id']
    assert replay.json()['stock_milliunits'] == 5000
    assert c.post(BASE + '/stock', json={**movement, 'quantity_milliunits': 6000}).status_code == 422
    issued = c.post(path, json={'tax_reviewed': True})
    assert issued.status_code == 200, issued.text
    assert issued.json()['totals']['total_paise'] == 23600
    assert c.post(path, json={'tax_reviewed': True}).json()['invoice_id'] == issued.json()['invoice_id']
    assert c.get(BASE + '/products').json()['products'][0]['stock_milliunits'] == 3000
    with Session(engine) as db:
        assert len(list(db.scalars(select(Invoice)))) == 1
        assert len(list(db.scalars(select(StockMovement)))) == 2


def test_partial_purchase_receipts_replay_and_over_receipt(api):
    c, _, _ = api
    product = setup(c)
    doc, _ = draft(c, product, 'purchase_order', 'PO-1', 5000)
    path = BASE + '/documents/' + doc['id']
    assert c.post(path + '/issue', json={'tax_reviewed': True}).status_code == 200
    receipt = {'line_index': 0, 'quantity_milliunits': 2000, 'request_key': 'delivery-1'}
    for _ in range(2):
        result = c.post(path + '/receive', json=receipt)
        assert result.status_code == 200, result.text
        assert result.json()['received'] == {'0': 2000}
    assert c.post(path + '/receive', json={**receipt, 'quantity_milliunits': 4000, 'request_key': 'delivery-2'}).status_code == 422
    assert c.post(path + '/receive', json={**receipt, 'quantity_milliunits': 1000}).status_code == 422
    assert c.get(BASE + '/products').json()['products'][0]['stock_milliunits'] == 2000
    assert c.post(path + '/cancel').status_code == 422


def test_independent_approval_and_read_only_tenant_boundaries(api):
    c, who, _ = api
    product = setup(c)
    assert c.post(BASE + '/profile', json={**PROFILE, 'require_approval': True}).status_code == 200
    doc, body = draft(c, product, 'estimate', 'EST-1')
    path = BASE + '/documents/' + doc['id']
    assert c.post(path + '/approve').status_code == 422
    assert c.post(path + '/issue', json={'tax_reviewed': True}).status_code == 422
    who['id'] = 'viewer'
    assert c.get(BASE + '/documents').status_code == 200
    for endpoint, payload in [('/products', PRODUCT), ('/profile', PROFILE), ('/documents', body)]:
        assert c.post(BASE + endpoint, json=payload).status_code == 403
    assert c.post(path + '/approve').status_code == 403
    who['id'] = 'approver'
    assert c.post(path + '/approve').status_code == 200
    assert c.post(path + '/issue', json={'tax_reviewed': True}).status_code == 200
    who['id'] = 'bob'
    assert c.get(BASE + '/products').status_code == 403
    assert c.post(path + '/cancel').status_code == 403


def test_foreign_references_rejected_and_supplier_snapshot_preserved(api):
    c, _, _ = api
    product = setup(c)
    doc, body = draft(c, product, 'estimate', 'EST-2')
    assert c.post(BASE + '/documents', json={**body, 'number': 'BAD-1', 'customer_id': 'cb'}).status_code == 422
    body['lines'][0]['product_id'] = 'foreign'
    assert c.post(BASE + '/documents', json={**body, 'number': 'BAD-2'}).status_code == 422
    assert c.post(BASE + '/profile', json={**PROFILE, 'legal_name': 'Changed name'}).status_code == 200
    stored = c.get(BASE + '/documents').json()['documents'][0]
    assert stored['supplier']['legal_name'] == 'Example Supplier'
    assert c.post(BASE + '/profile', json={**PROFILE, 'gstin': '29ABCDE1234F1Z5'}).status_code == 422
    assert c.post(BASE + '/products', json={**PRODUCT, 'unit_price_paise': True}).status_code == 422
