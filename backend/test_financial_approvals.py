import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,select,func
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from auth_identity import get_verified_identity
from financial_approvals import FinancialApproval
from financial_approvals_api import router
from finance_api import router as finance_router
from saas_api import router as invoice_router,get_saas_session
from saas_domain import SaaSBase,Organization,Membership,Customer,Invoice,InvoiceMemo,Payment,InvoiceRefund
from intelligence_api import today


@pytest.fixture
def api():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool);SaaSBase.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([Organization(id='a',name='A',mode='b2b'),Organization(id='b',name='B',mode='b2b')]);db.flush()
        for user,role in [('owner','owner'),('approver','admin'),('accountant','accountant'),('viewer','viewer')]:db.add(Membership(organization_id='a',user_id=user,role=role))
        db.add(Membership(organization_id='b',user_id='bob',role='owner'));db.add(Customer(id='buyer',organization_id='a',name='Buyer'));db.flush();db.add(Invoice(id='inv',organization_id='a',customer_id='buyer',invoice_number='INV',total_paise=10000,due_date=today()));db.commit()
    app=FastAPI();app.include_router(router);app.include_router(finance_router);app.include_router(invoice_router);who={'id':'owner'};app.dependency_overrides[get_verified_identity]=lambda:who['id']
    def session():
        with Session(engine) as db:yield db
    app.dependency_overrides[get_saas_session]=session
    with TestClient(app) as c:yield c,who,engine
    engine.dispose()


BASE='/api/v1/organizations/a'
QUEUE=BASE+'/financial-approvals'
def request_memo(c,key='memo-1',amount=1000):return c.post(QUEUE,json={'invoice_id':'inv','operation':'memo','memo':{'kind':'credit','number':key,'amount_paise':amount,'reason':'Reviewed internal adjustment'},'request_key':key})
def decide(c,rid,decision='approve'):return c.post(QUEUE+'/'+rid+'/decision',json={'decision':decision,'note':'Independent review of supporting records'})


def test_policy_blocks_direct_posts_and_requires_independent_active_approval(api):
    c,who,engine=api;assert c.post(QUEUE+'/policy',json={'require_approval':True}).status_code==200
    direct=c.post(BASE+'/invoices/inv/memos',json={'kind':'credit','number':'DIRECT','amount_paise':1000,'reason':'Bypass attempt'});assert direct.status_code==422
    first=request_memo(c);assert first.status_code==201;rid=first.json()['id'];assert request_memo(c).json()['id']==rid
    assert decide(c,rid).status_code==422
    who['id']='viewer';assert decide(c,rid).status_code==403;assert request_memo(c,'viewer').status_code==403
    who['id']='approver';posted=decide(c,rid);assert posted.status_code==200;assert posted.json()['status']=='approved';assert decide(c,rid).json()['posted_id']==posted.json()['posted_id']
    with Session(engine) as db:assert db.scalar(select(func.count()).select_from(InvoiceMemo))==1
    assert c.get(BASE+'/invoices/inv/ledger').json()['outstanding_paise']==9000


def test_creator_role_revocation_and_owner_policy_controls_are_rechecked(api):
    c,who,engine=api;who['id']='accountant';rid=request_memo(c).json()['id'];assert c.post(QUEUE+'/policy',json={'require_approval':True}).status_code==403
    with Session(engine) as db:db.get(Membership,('a','accountant')).active=False;db.commit()
    who['id']='approver';assert decide(c,rid).status_code==422
    assert decide(c,rid,'reject').status_code==200
    assert c.post(QUEUE+'/policy',json={'require_approval':True}).status_code==403
    who['id']='owner'
    with Session(engine) as db:db.get(Membership,('a','approver')).active=False;db.commit()
    assert c.post(QUEUE+'/policy',json={'require_approval':True}).status_code==422
    who['id']='bob';assert c.get(QUEUE).status_code==403;assert decide(c,rid).status_code==403


def test_refund_approval_rechecks_credit_and_rolls_back_decision_on_failure(api):
    c,who,engine=api
    with Session(engine) as db:
        db.add(Payment(organization_id='a',invoice_id='inv',amount_paise=10000,idempotency_key='paid'))
        db.add(InvoiceMemo(organization_id='a',invoice_id='inv',kind='credit',number='credit',amount_paise=3000,reason='Credit',actor_id='owner'));db.commit()
    c.post(QUEUE+'/policy',json={'require_approval':True})
    payload={'invoice_id':'inv','operation':'refund_record','refund':{'amount_paise':2000,'reason':'Externally completed refund reference','confirmed_external_refund':True},'request_key':'refund-request'}
    assert c.post(BASE+'/invoices/inv/refunds',json={**payload['refund'],'idempotency_key':'bypass'}).status_code==422
    rid=c.post(QUEUE,json=payload).json()['id'];assert c.post(QUEUE,json={**payload,'refund':{**payload['refund'],'amount_paise':1000}}).status_code==422
    with Session(engine) as db:db.add(InvoiceRefund(organization_id='a',invoice_id='inv',amount_paise=2000,reason='Other recorded refund',idempotency_key='other',actor_id='owner'));db.commit()
    who['id']='approver';assert decide(c,rid).status_code==422
    with Session(engine) as db:assert db.get(FinancialApproval,rid).status=='pending';assert db.scalar(select(func.count()).select_from(InvoiceRefund))==1
    assert decide(c,rid,'reject').status_code==200
    who['id']='owner'
    approved=c.post(QUEUE,json={**payload,'request_key':'refund-valid','refund':{**payload['refund'],'amount_paise':1000}}).json()['id']
    who['id']='approver';assert decide(c,approved).status_code==200
    assert c.get(BASE+'/invoices/inv/ledger').json()['credit_balance_paise']==0


def test_accountants_cannot_request_refunds_or_cancel_another_request(api):
    c,who,engine=api;rid=request_memo(c).json()['id'];who['id']='accountant'
    assert decide(c,rid,'cancel').status_code==403
    assert c.post(QUEUE,json={'invoice_id':'inv','operation':'refund_record','refund':{'amount_paise':1000,'reason':'External refund','confirmed_external_refund':True},'request_key':'bad-role'}).status_code==403
    own=request_memo(c,'own').json()['id'];assert decide(c,own,'cancel').status_code==200
