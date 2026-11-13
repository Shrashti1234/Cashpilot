from test_financial_approvals import api
from business_clock import india_today
from collection_worklist_api import router
from saas_domain import Invoice, Payment
from sqlalchemy.orm import Session


PATH = '/api/v1/organizations/a/collections/worklist'


def test_worklist_assignment_is_tenant_scoped_and_read_only_for_viewers(api):
    client, who, _ = api
    client.app.include_router(router)
    body = {'assignee': 'accountant', 'follow_up': str(india_today()), 'note': 'Check the open balance'}
    assert client.post(PATH + '/inv', json={**body, 'assignee': 'bob'}).status_code == 422
    assert client.post(PATH + '/inv', json=body).status_code == 200
    row = client.get(PATH).json()['actions'][0]
    assert row['reference'] == 'INV'
    assert row['task'] == {**body, 'active': True}
    who['id'] = 'viewer'
    assert client.get(PATH).status_code == 200
    assert client.post(PATH + '/inv', json=body).status_code == 403


def test_worklist_filters_before_pagination_and_omits_settled_invoices(api):
    client, who, engine = api
    client.app.include_router(router)
    today = india_today()
    with Session(engine) as db:
        for n in range(120):
            db.add(Invoice(id=f'i{n:03}', organization_id='a', customer_id='buyer',
                           invoice_number=f'BILL-{n:03}', due_date=today, total_paise=100))
        db.flush()
        db.add(Payment(organization_id='a', invoice_id='i000', amount_paise=100, idempotency_key='settle-000'))
        db.commit()
    assert client.post(PATH + '/i119', json={'assignee':'accountant','follow_up':str(today)}).status_code == 200
    who['id'] = 'accountant'
    mine = client.get(PATH, params={'view':'mine','page_size':1}).json()
    assert mine['total'] == 1 and mine['actions'][0]['reference'] == 'BILL-119'
    due = client.get(PATH, params={'view':'due'}).json()
    assert due['total'] == 1 and due['actions'][0]['reference'] == 'BILL-119'
    first = client.get(PATH, params={'page_size':50}).json()
    last = client.get(PATH, params={'page_size':50,'page':3}).json()
    assert first['total'] == last['total'] == 120 and len(last['actions']) == 20
    assert not {r['invoice_id'] for r in first['actions']} & {r['invoice_id'] for r in last['actions']}
    assert client.get(PATH, params={'q':'BILL-000'}).json()['total'] == 0
    assert client.get(PATH, params={'q':'BILL-11%'}).json()['total'] == 0
    who['id'] = 'bob'
    assert client.get(PATH).status_code == 403


def test_accountant_can_claim_but_cannot_reassign_another_members_follow_up(api):
    client, who, _ = api
    client.app.include_router(router)
    body = {'assignee': 'accountant', 'follow_up': str(india_today())}
    who['id'] = 'accountant'
    assert client.post(PATH + '/inv', json=body).status_code == 200
    assert client.post(PATH + '/inv', json={**body, 'assignee': 'owner'}).status_code == 403
    who['id'] = 'owner'
    assert client.post(PATH + '/inv', json={**body, 'assignee': 'owner'}).status_code == 200
    who['id'] = 'accountant'
    assert client.post(PATH + '/inv', json=body).status_code == 403
