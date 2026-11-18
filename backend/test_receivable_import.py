from sqlalchemy import select, func
from sqlalchemy.orm import Session
from test_financial_approvals import api
from receivable_import_api import router
from saas_domain import Invoice, Payment
from operations import BusinessProfile

PATH = '/api/v1/organizations/a/receivable-import'
BODY = {'content': 'Party,Bill,Due on,Pending\nBuyer,TALLY-1,30/10/2026,"1,23,456.78"\nNew buyer,TALLY-2,2026-10-31,10.01',
        'columns': {'customer': 'Party', 'reference': 'Bill', 'due': 'Due on', 'amount': 'Pending'}}


def test_preview_and_replay_preserve_opening_balance_without_recording_cash(api):
    client, _, engine = api
    client.app.include_router(router)
    result = client.post(PATH + '/preview', json=BODY).json()
    assert result['ready_paise'] == 12_346_679
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Invoice)) == 1
    data = {**BODY, 'preview_digest': result['preview_digest']}
    assert client.post(PATH + '/commit', json=data).json() == {'imported': 2, 'duplicates': 0}
    assert client.post(PATH + '/commit', json=data).json() == {'imported': 0, 'duplicates': 2}
    summary = client.get('/api/v1/organizations/a/invoices/summary').json()
    assert summary['total_invoiced_paise'] == summary['adjusted_invoiced_paise'] == 10000
    assert summary['outstanding_paise'] == 12_356_679
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Payment)) == 0


def test_bad_row_blocks_whole_import_and_viewer_cannot_preview(api):
    client, who, engine = api
    client.app.include_router(router)
    body = {**BODY, 'content': BODY['content'].replace('10.01', '1.001')}
    result = client.post(PATH + '/preview', json=body).json()
    assert result['errors'] == 1 and result['rows'][1]['row'] == 3
    assert client.post(PATH + '/commit', json={**body, 'preview_digest': result['preview_digest']}).status_code == 422
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Invoice)) == 1
    who['id'] = 'viewer'
    assert client.post(PATH + '/preview', json=BODY).status_code == 403


def test_stale_customer_mapping_and_approval_policy_block_commit(api):
    client, _, engine = api
    client.app.include_router(router)
    result = client.post(PATH + '/preview', json=BODY).json()
    data = {**BODY, 'preview_digest': result['preview_digest']}
    assert client.post('/api/v1/organizations/a/customers', json={'name': 'New buyer'}).status_code == 201
    assert client.post(PATH + '/commit', json=data).status_code == 409
    with Session(engine) as db:
        db.add(BusinessProfile(organization_id='a', legal_name='Pilot', address='Address', gstin='', state_code='27', require_approval=True))
        db.commit()
    result = client.post(PATH + '/preview', json=BODY).json()
    assert result['blocked_by_approval'] is True
    assert client.post(PATH + '/commit', json={**BODY, 'preview_digest': result['preview_digest']}).status_code == 422
