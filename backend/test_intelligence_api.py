from datetime import timedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine,select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from auth_identity import get_verified_identity
from cash_ledger import CashEntry
from intelligence_api import router,today
from saas_api import get_saas_session
from saas_api import router as invoices_router
from disputes_api import router as disputes_router
from saas_domain import SaaSBase,Organization,Membership


@pytest.fixture
def api():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    SaaSBase.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([Organization(id='a',name='A',mode='micro'),Organization(id='b',name='B',mode='micro')]);db.flush()
        db.add_all([Membership(organization_id='a',user_id='alice',role='owner'),Membership(organization_id='b',user_id='bob',role='viewer')]);db.commit()
    app=FastAPI();app.include_router(router);app.include_router(invoices_router);app.include_router(disputes_router);identity={'user':'alice'}
    app.dependency_overrides[get_verified_identity]=lambda:identity['user']
    def session():
        with Session(engine) as db: yield db
    app.dependency_overrides[get_saas_session]=session
    with TestClient(app) as client: yield client,identity,engine
    engine.dispose()


def test_demo_is_authorized_read_only_and_cross_tenant_scenarios_fail(api):
    c,identity,engine=api
    payload={'opening_balance_paise':1500000,'horizon_days':7,'use_demo':True}
    r=c.post('/api/v1/organizations/a/decision-lab/simulate',json=payload)
    assert r.status_code==200,r.text
    assert r.json()['data_source']=='synthetic_demo'
    with Session(engine) as db: assert list(db.scalars(select(CashEntry)))==[]
    identity['user']='bob'
    for path in ['/cash-entries','/intelligence/model']:
        assert c.get('/api/v1/organizations/a'+path).status_code==403
    assert c.post('/api/v1/organizations/a/decision-lab/simulate',json=payload).status_code==403
    assert c.post('/api/v1/organizations/b/decision-lab/simulate',json=payload).status_code==200


def test_csv_is_atomic_precise_and_viewers_cannot_write(api):
    c,identity,engine=api
    header='date,direction,status,amount_inr,description\n'
    good=f'{today()},out,actual,12.34,Lunch\n'
    bad=f'{today()},out,actual,1.234,Bad precision\n'
    path='/api/v1/organizations/a/cash-entries/import'
    assert c.post(path,json={'csv_text':header+good+bad}).status_code==422
    assert c.get('/api/v1/organizations/a/cash-entries').json()['entries']==[]
    assert c.post(path,json={'csv_text':header+good}).status_code==201
    assert c.get('/api/v1/organizations/a/cash-entries').json()['entries'][0]['amount_paise']==1234
    identity['user']='bob'
    assert c.post('/api/v1/organizations/b/cash-entries/import',json={'csv_text':header+good}).status_code==403


def test_future_actual_and_negative_amount_rejected(api):
    c,_,_=api
    body={'entry_date':str(today()+timedelta(days=1)),'direction':'out','status':'actual','amount_paise':100,'description':'Invalid future actual'}
    assert c.post('/api/v1/organizations/a/cash-entries',json=body).status_code==422
    body.update(entry_date=str(today()),amount_paise=-100)
    assert c.post('/api/v1/organizations/a/cash-entries',json=body).status_code==422


def test_cash_entries_can_be_corrected_or_voided_without_cross_tenant_writes(api):
    c,identity,_=api
    body={'entry_date':str(today()),'direction':'out','status':'actual','amount_paise':10000,'description':'Operating expense'}
    created=c.post('/api/v1/organizations/a/cash-entries',json=body)
    assert created.status_code==201
    entry_id=created.json()['id']
    body['status']='void'
    assert c.post('/api/v1/organizations/a/cash-entries/'+entry_id,json=body).json()['status']=='void'
    identity['user']='bob'
    assert c.post('/api/v1/organizations/a/cash-entries/'+entry_id,json=body).status_code==403


def test_live_scenario_rejects_unowned_ids_and_does_not_pretend_to_use_model_without_history(api):
    c,_,_=api
    body={'opening_balance_paise':10000,'horizon_days':30,'use_demo':False}
    r=c.post('/api/v1/organizations/a/decision-lab/simulate',json=body)
    assert r.status_code==200
    assert r.json()['expense_method']=='no_expense_history'
    body['receipt_overrides']=[{'invoice_id':'foreign','receipt_date':str(today())}]
    assert c.post('/api/v1/organizations/a/decision-lab/simulate',json=body).status_code==422


def test_dispute_state_transitions_and_audit_are_tenant_scoped(api):
    c,identity,_=api
    base='/api/v1/organizations/a'
    customer=c.post(base+'/customers',json={'name':'Buyer'}).json()
    invoice=c.post(base+'/invoices',json={'customer_id':customer['id'],'invoice_number':'D-1','due_date':str(today()),'total_paise':10000}).json()
    opened=c.post(base+'/disputes',json={'invoice_id':invoice['id'],'reason':'quality','description':'Review delivery'})
    assert opened.status_code==201
    path=base+'/disputes/'+opened.json()['id']+'/status'
    assert c.post(path,json={'status':'resolved','resolution_note':'Invalid shortcut'}).status_code==422
    assert c.post(path,json={'status':'under_review'}).status_code==200
    assert c.post(path,json={'status':'resolved'}).status_code==422
    assert c.post(path,json={'status':'resolved','resolution_note':'Agreed with customer'}).status_code==200
    events=c.get(base+'/audit').json()['events']
    assert {'customer.created','invoice.created','dispute.opened','dispute.under_review','dispute.resolved'}<={e['action'] for e in events}
    identity['user']='bob'
    assert c.get(base+'/audit').status_code==403
    assert c.get(base+'/disputes').status_code==403
    assert c.post(path,json={'status':'under_review'}).status_code==403


def test_simulation_rate_limit_recovers_after_window(monkeypatch):
    import request_limits
    from fastapi import HTTPException
    clock={'time':100.0}
    monkeypatch.setattr(request_limits,'_requests',{})
    monkeypatch.setattr(request_limits,'monotonic',lambda:clock['time'])
    for _ in range(20):request_limits.allow_simulation('alice','a')
    with pytest.raises(HTTPException) as exc:request_limits.allow_simulation('alice','a')
    assert exc.value.status_code==429
    clock['time']+=61
    request_limits.allow_simulation('alice','a')
