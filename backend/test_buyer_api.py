from datetime import datetime,timedelta,timezone
import hashlib
import hmac
import json

import httpx
import pytest
from fastapi import FastAPI,HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from api_security import safe_validation_error
from auth_identity import get_verified_identity
from buyer_access import BuyerAccess
from buyer_api import router
from intelligence_api import today,router as intelligence_router
from operations import BusinessProfile
from promises import PaymentPromise
import razorpay_checkout
from saas_api import get_saas_session,router as invoices_router
from finance_api import router as finance_router
from saas_domain import SaaSBase,Organization,Membership,Customer,Invoice,InvoiceMemo


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr('request_limits._requests',{})
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool);SaaSBase.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([Organization(id='a',name='Acme',mode='b2b'),Organization(id='b',name='Secret foreign business',mode='b2b')]);db.flush()
        db.add_all([Membership(organization_id='a',user_id='owner',role='owner'),Membership(organization_id='a',user_id='viewer',role='viewer'),Membership(organization_id='b',user_id='bob',role='owner'),Customer(id='ca',organization_id='a',name='Buyer'),Customer(id='cb',organization_id='b',name='Secret foreign buyer')]);db.flush()
        db.add_all([Invoice(id='ia',organization_id='a',customer_id='ca',invoice_number='SHARED-1',due_date=today()-timedelta(days=2),total_paise=10000),Invoice(id='ib',organization_id='b',customer_id='cb',invoice_number='SECRET-1',due_date=today(),total_paise=90000),BusinessProfile(organization_id='a',legal_name='Acme seller',address='Supplier address',gstin='',state_code='27',require_approval=False)]);db.flush()
        db.add(InvoiceMemo(organization_id='a',invoice_id='ia',kind='credit',number='PRIVATE-CR',amount_paise=1000,reason='SENSITIVE_INTERNAL_STRATEGY',actor_id='owner'));db.commit()
    app=FastAPI();app.include_router(router);app.include_router(invoices_router);app.include_router(intelligence_router);app.include_router(finance_router)
    app.include_router(razorpay_checkout.router)
    app.add_exception_handler(RequestValidationError,safe_validation_error)
    who={'id':'owner'}
    def identity():
        if who['id'] is None:raise HTTPException(401,'Missing authentication')
        return who['id']
    app.dependency_overrides[get_verified_identity]=identity
    def session():
        with Session(engine) as db:yield db
    app.dependency_overrides[get_saas_session]=session
    with TestClient(app) as c:yield c,who,engine
    engine.dispose()


BASE='/api/v1/organizations/a'


@pytest.fixture
def razorpay_test_mode(monkeypatch):
    for name, value in {
        'ORGANIZATION_ID': 'a', 'ACCOUNT_ID': 'acc_Sandbox', 'KEY_ID': 'rzp_test_Sandbox',
        'KEY_SECRET': 'test-key', 'WEBHOOK_SECRET': 'test-webhook',
    }.items():
        monkeypatch.setenv('RAZORPAY_TEST_'+name, value)
    links = {}
    calls = []

    def request(method, url, *, auth, timeout, **kwargs):
        assert url == 'https://api.razorpay.com/v1/payment_links'
        assert auth == ('rzp_test_Sandbox', 'test-key')
        calls.append(method)
        original = httpx.Request(method,url)
        if method == 'GET':
            existing = links.get(kwargs['params']['reference_id'])
            return httpx.Response(200,request=original,json={'payment_links':[existing] if existing else []})
        body = kwargs['json']
        assert body['accept_partial'] is False and body['reminder_enable'] is False
        assert body['notify'] == {'email':False,'sms':False}
        assert 'customer' not in body and body['amount'] == 9000
        links[body['reference_id']] = {**body,'id':'plink_Test1','status':'created',
                                      'short_url':'https://rzp.io/rzp/Test1','order_id':'order_Test1'}
        # Model a provider-side success whose response never reached CashPilot.
        raise httpx.ReadTimeout('Simulated lost response', request=original)

    monkeypatch.setattr(razorpay_checkout.httpx,'request',request)
    return links,calls


def test_razorpay_checkout_recovery_and_signed_receipt(api,razorpay_test_mode):
    c,who,_=api
    provider_links,calls=razorpay_test_mode
    token=link(c,can_pay=True)['token']
    checkout='/api/v1/buyer/checkout'
    inspect='/api/v1/buyer/inspect'
    webhook='/api/v1/webhooks/razorpay/test'
    who['id']=None
    body={'token':token}
    assert c.post(inspect,json=body).json()['payment_provider_connected'] is True
    assert c.post(checkout,json=body).status_code==502
    recovered=c.post(checkout,json=body)
    assert recovered.status_code==200,recovered.text
    assert recovered.json()['checkout_url']=='https://rzp.io/rzp/Test1'
    assert c.post(checkout,json=body).json()==recovered.json()
    assert calls==['GET','POST','GET']
    provider=next(iter(provider_links.values()))

    def deliver(*, signature=True, amount=9000, account='acc_Sandbox', status='captured'):
        event={'event':'payment_link.paid','account_id':account,'payload':{
            'payment_link':{'entity':{**provider,'status':'paid','amount_paid':9000}},
            'payment':{'entity':{'id':'pay_Test1','order_id':'order_Test1','amount':amount,
                                 'currency':'INR','status':status}},
        }}
        raw=json.dumps(event,indent=2).encode()
        digest=hmac.new(b'test-webhook',raw,hashlib.sha256).hexdigest()
        return c.post(webhook,content=raw,headers={'X-Razorpay-Signature':digest if signature else '0'*64})

    assert deliver(signature=False).status_code==401
    assert deliver(account='acc_Other').status_code==403
    assert deliver(amount=8999).status_code==409
    assert deliver(status='authorized').status_code==409
    assert c.post(inspect,json=body).json()['outstanding_paise']==9000
    assert deliver().json()=={'status':'recorded'}
    assert deliver().json()=={'status':'already_recorded'}
    buyer=c.post(inspect,json=body).json()
    assert buyer['outstanding_paise']==0 and buyer['net_received_paise']==9000
    assert buyer['payment_provider_connected'] is False
    who['id']='owner'
    receipts=c.get(BASE+'/invoices/ia/payments').json()['payments']
    assert len(receipts)==1 and receipts[0]['amount_paise']==9000
    assert c.post(BASE+'/invoices/ia/payments',json={
        'amount_paise':9000,'idempotency_key':'razorpay-test:pay_Test1'}).status_code==422


def test_razorpay_is_workspace_scoped_and_requires_payment_permission(api,razorpay_test_mode,monkeypatch):
    c,who,_=api
    assert c.get(BASE+'/buyer-access').json()['razorpay_test_configured'] is True
    no_pay=link(c)['token']
    allowed=link(c,can_pay=True)
    who['id']='bob'
    foreign='/api/v1/organizations/b/buyer-access'
    assert c.get(foreign).json()['razorpay_test_configured'] is False
    assert c.post(foreign,json={'invoice_id':'ib','can_pay':True}).status_code==422
    who['id']=None
    checkout='/api/v1/buyer/checkout'
    assert c.post(checkout,json={'token':no_pay}).status_code==403
    assert c.post('/api/v1/buyer/dispute',json={
        'token':allowed['token'],'reason':'quality','description':'Review before paying'}).status_code==201
    assert c.post(checkout,json={'token':allowed['token']}).status_code==409
    monkeypatch.setenv('RAZORPAY_TEST_KEY_ID','rzp_live_WrongMode')
    assert c.post(checkout,json={'token':allowed['token']}).status_code==403
    assert razorpay_test_mode[1]==[]


def link(c,**options):
    r=c.post(BASE+'/buyer-access',json={'invoice_id':'ia','expires_days':7,'can_dispute':True,'can_promise':True,**options})
    assert r.status_code==201,r.text
    return r.json()


def test_private_access_is_hash_only_expiring_revocable_and_scoped(api):
    c,who,engine=api;created=link(c);token=created['token']
    with Session(engine) as db:assert db.get(BuyerAccess,created['id']).token_hash==hashlib.sha256(token.encode()).hexdigest()
    assert 'token' not in c.get(BASE+'/buyer-access').json()['links'][0]
    who['id']=None
    r=c.post('/api/v1/buyer/inspect',json={'token':token});assert r.status_code==200,r.text
    assert r.headers['cache-control']=='no-store'
    assert r.json()['invoice_number']=='SHARED-1' and r.json()['outstanding_paise']==9000
    assert all(value not in r.text for value in ['SECRET-1','Secret foreign','SENSITIVE_INTERNAL_STRATEGY','PRIVATE-CR','actor_id','training_provenance'])
    forged=c.post('/api/v1/buyer/inspect',json={'token':token,'invoice_id':'ib'})
    assert forged.status_code==422 and token not in forged.text
    assert c.get(BASE+'/buyer-access').status_code==401
    who['id']='owner';assert c.post(BASE+'/buyer-access/'+created['id']+'/revoke').status_code==200
    who['id']=None;assert c.post('/api/v1/buyer/inspect',json={'token':token}).status_code==404
    who['id']='owner';expired=link(c)
    with Session(engine) as db:db.get(BuyerAccess,expired['id']).expires_at=datetime.now(timezone.utc)-timedelta(seconds=1);db.commit()
    who['id']=None;assert c.post('/api/v1/buyer/inspect',json={'token':expired['token']}).status_code==404


def test_buyer_promises_do_not_become_receipts_and_follow_actual_settlement(api):
    c,who,_=api;created=link(c);who['id']=None
    body={'token':created['token'],'amount_paise':2000,'promised_date':str(today()+timedelta(days=2)),'note':'Shared promise','request_key':'p1'}
    r=c.post('/api/v1/buyer/promise',json=body);assert r.status_code==201,r.text
    pid=r.json()['id'];assert c.post('/api/v1/buyer/promise',json=body).json()['id']==pid
    assert c.post('/api/v1/buyer/promise',json={**body,'amount_paise':9500,'request_key':'p2'}).status_code==422
    who['id']='owner'
    assert c.get(BASE+'/invoices/ia/ledger').json()['paid_paise']==0
    assert c.get(BASE+'/invoices').json()['invoices'][0]['outstanding_paise']==9000
    assert c.get(BASE+'/collections/plan').json()['actions'][0]['action']=='review_promise'
    assert c.post(BASE+'/invoices/ia/memos',json={'kind':'credit','number':'PRIVATE-2','amount_paise':2000,'reason':'Another internal adjustment'}).status_code==201
    who['id']=None
    before_receipt=c.post('/api/v1/buyer/inspect',json={'token':created['token']}).json()
    assert before_receipt['promises'][0]['state']=='pending' and before_receipt['outstanding_paise']==7000
    who['id']='owner'
    assert c.post(BASE+'/invoices/ia/payments',json={'amount_paise':2000,'idempotency_key':'actual-receipt'}).status_code==201
    who['id']=None
    view=c.post('/api/v1/buyer/inspect',json={'token':created['token']}).json()
    assert view['outstanding_paise']==5000 and view['promises'][0]['state']=='fulfilled'
    assert 'note' not in view['promises'][0] and 'cancellation_note' not in view['promises'][0]


def test_guest_dispute_is_invoice_scoped_and_excluded_from_simulation_receipts(api):
    c,who,_=api;created=link(c);who['id']=None
    body={'token':created['token'],'reason':'quality','description':'Please review the delivery'}
    assert c.post('/api/v1/buyer/dispute',json=body).status_code==201
    assert c.post('/api/v1/buyer/dispute',json=body).status_code==201
    who['id']='owner'
    simulation=c.post(BASE+'/decision-lab/simulate',json={'opening_balance_paise':0,'horizon_days':7,'use_demo':False})
    assert simulation.status_code==200,simulation.text
    assert simulation.json()['invoice_risks'][0]['disputed'] is True
    assert simulation.json()['baseline']['closing_median_paise']==0


def test_permissions_member_roles_and_internal_cancellation_notes_are_protected(api):
    c,who,_=api;readonly=link(c,can_promise=False,can_dispute=False)
    who['id']=None
    promise={'token':readonly['token'],'amount_paise':1000,'promised_date':str(today()),'note':'Test','request_key':'deny'}
    assert c.post('/api/v1/buyer/promise',json=promise).status_code==403
    assert c.post('/api/v1/buyer/dispute',json={'token':readonly['token'],'reason':'other','description':'Denied'}).status_code==403
    who['id']='viewer';assert c.post(BASE+'/buyer-access',json={'invoice_id':'ia'}).status_code==403
    who['id']='bob';assert c.get(BASE+'/buyer-access').status_code==403
    who['id']='owner';created=link(c)
    who['id']=None;promise.update(token=created['token'],request_key='valid')
    pid=c.post('/api/v1/buyer/promise',json=promise).json()['id']
    who['id']='owner';assert c.post(BASE+'/collections/promises/'+pid+'/cancel',json={'reason':'PRIVATE_CANCELLATION_REASON'}).status_code==200
    who['id']=None;r=c.post('/api/v1/buyer/promise',json=promise)
    assert r.json()['state']=='cancelled' and 'PRIVATE_CANCELLATION_REASON' not in r.text
