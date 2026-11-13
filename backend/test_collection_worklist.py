from test_financial_approvals import api
from business_clock import india_today
from collection_worklist_api import router


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
