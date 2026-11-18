from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from auth_identity import get_verified_identity
from finance_api import router
from intelligence_api import router as intelligence_router
from saas_api import get_saas_session, router as invoices_router
from saas_domain import SaaSBase, Organization, Membership, Customer


@pytest.fixture
def api():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    @event.listens_for(engine,'connect')
    def fk_on(c,_): c.execute('PRAGMA foreign_keys=ON')
    SaaSBase.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([Organization(id='a',name='A',mode='micro'),Organization(id='b',name='B',mode='micro')]);db.flush()
        db.add_all([Membership(organization_id='a',user_id='owner',role='owner'),Membership(organization_id='a',user_id='viewer',role='viewer'),Membership(organization_id='a',user_id='accountant',role='accountant'),Membership(organization_id='b',user_id='bob',role='owner'),Customer(id='buyer',organization_id='a',name='Buyer')]);db.commit()
    app=FastAPI();app.include_router(router);app.include_router(invoices_router);app.include_router(intelligence_router)
    user={'id':'owner'};app.dependency_overrides[get_verified_identity]=lambda:user['id']
    def session():
        with Session(engine) as db:yield db
    app.dependency_overrides[get_saas_session]=session
    with TestClient(app) as c:yield c,user
    engine.dispose()


BASE='/api/v1/organizations/a'


def invoice(c,number='INV-1'):
    r=c.post(BASE+'/invoices',json={'customer_id':'buyer','invoice_number':number,'due_date':str(date.today()),'total_paise':10000})
    assert r.status_code==201,r.text
    return r.json()['id']


def test_credits_refunds_debits_and_statements_conserve_the_customer_balance(api):
    c,_=api;inv=invoice(c);path=BASE+'/invoices/'+inv
    assert c.post(path+'/payments',json={'amount_paise':8000,'idempotency_key':'p1'}).status_code==201
    credit={'kind':'credit','number':'CR-1','amount_paise':5000,'reason':'Agreed service reduction'}
    first=c.post(path+'/memos',json=credit)
    assert first.status_code==201,first.text
    assert c.post(path+'/memos',json=credit).json()['id']==first.json()['id']
    position=c.get(path+'/ledger').json()
    assert (position['effective_total_paise'],position['paid_paise'],position['credit_balance_paise'],position['outstanding_paise'])==(5000,8000,3000,0)
    refund={'amount_paise':2000,'reason':'Bank transfer REF-1 completed','idempotency_key':'refund-1','confirmed_external_refund':True}
    r=c.post(path+'/refunds',json=refund);assert r.status_code==201,r.text
    assert c.post(path+'/refunds',json=refund).json()['id']==r.json()['id']
    assert c.post(path+'/refunds',json={**refund,'amount_paise':1001,'idempotency_key':'refund-2'}).status_code==422
    assert c.post(path+'/memos',json={'kind':'debit','number':'DR-1','amount_paise':1500,'reason':'Additional agreed work'}).status_code==201
    assert c.get(path+'/ledger').json()['outstanding_paise']==500
    assert c.post(path+'/payments',json={'amount_paise':501,'idempotency_key':'too-much'}).status_code==422
    assert c.post(path+'/payments',json={'amount_paise':500,'idempotency_key':'p2'}).status_code==201
    statement=c.get(BASE+'/customers/buyer/statement').json()
    assert statement['totals']['effective_total_paise']==6500
    assert statement['totals']['gross_paid_paise']==8500
    assert statement['totals']['refunded_paise']==2000
    assert statement['totals']['net_due_paise']==0
    assert statement['totals']['credit_balance_paise']==0
    assert c.get(BASE+'/invoices/summary').json()['outstanding_paise']==0


def test_adjusted_balances_reach_collections_and_decision_lab(api):
    c,_=api;inv=invoice(c);path=BASE+'/invoices/'+inv
    assert c.post(path+'/memos',json={'kind':'credit','number':'CR-2','amount_paise':4000,'reason':'Agreed adjustment'}).status_code==201
    assert c.get(BASE+'/collections/plan').json()['total_outstanding_paise']==6000
    simulation=c.post(BASE+'/decision-lab/simulate',json={'opening_balance_paise':0,'horizon_days':7,'use_demo':False})
    assert simulation.status_code==200,simulation.text
    assert simulation.json()['invoice_risks'][0]['outstanding_paise']==6000
    assert simulation.json()['invoice_risks'][0]['history_count']==0
    assert c.post(path+'/memos',json={'kind':'credit','number':'CR-3','amount_paise':6001,'reason':'Invalid excess credit'}).status_code==422
    assert c.get(path+'/ledger').json()['effective_total_paise']==6000


def test_roles_foreign_tenants_and_confirmation_are_enforced(api):
    c,user=api;inv=invoice(c);path=BASE+'/invoices/'+inv
    refund={'amount_paise':1,'reason':'Test','idempotency_key':'r','confirmed_external_refund':False}
    assert c.post(path+'/refunds',json=refund).status_code==422
    user['id']='viewer'
    assert c.get(path+'/ledger').status_code==200
    assert c.post(path+'/memos',json={'kind':'credit','number':'CR-4','amount_paise':1,'reason':'No permission'}).status_code==403
    user['id']='accountant'
    assert c.post(path+'/refunds',json={**refund,'confirmed_external_refund':True}).status_code==403
    user['id']='bob'
    assert c.get(path+'/ledger').status_code==403
    assert c.get(BASE+'/customers/buyer/statement').status_code==403
    assert c.post(path+'/memos',json={'kind':'credit','number':'CR-4','amount_paise':1,'reason':'Wrong business'}).status_code==403


def test_memo_and_refund_replay_reject_changed_payloads(api):
    c,_=api;inv=invoice(c);path=BASE+'/invoices/'+inv
    assert c.post(path+'/payments',json={'amount_paise':10000,'idempotency_key':'p'}).status_code==201
    memo={'kind':'credit','number':'CR-5','amount_paise':5000,'reason':'Reduction'}
    assert c.post(path+'/memos',json=memo).status_code==201
    assert c.post(path+'/memos',json={**memo,'amount_paise':4000}).status_code==422
    refund={'amount_paise':1000,'reason':'Completed reference','idempotency_key':'r','confirmed_external_refund':True}
    assert c.post(path+'/refunds',json=refund).status_code==201
    assert c.post(path+'/refunds',json={**refund,'amount_paise':500}).status_code==422
    assert c.get(path+'/ledger').json()['refunded_paise']==1000
