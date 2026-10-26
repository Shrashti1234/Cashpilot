from datetime import timedelta
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,select,func
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from auth_identity import get_verified_identity
from contacts import ContactRecord,ContactPreference,ContactConsentChange
from contacts_api import router
from disputes import InvoiceDispute
from intelligence_api import today
from promises import create_promise
from saas_api import get_saas_session,router as invoice_router
from saas_domain import SaaSBase,Organization,Membership,Customer,Invoice,Payment


@pytest.fixture
def api():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool);SaaSBase.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([Organization(id='a',name='Shop',mode='b2b'),Organization(id='b',name='Foreign',mode='b2b')]);db.flush();db.add_all([Membership(organization_id='a',user_id='owner',role='owner'),Membership(organization_id='a',user_id='accountant',role='accountant'),Membership(organization_id='a',user_id='viewer',role='viewer'),Membership(organization_id='b',user_id='bob',role='owner'),Customer(id='buyer',organization_id='a',name='Buyer')]);db.flush()
        for i in ['one','two']:db.add(Invoice(id=i,organization_id='a',customer_id='buyer',invoice_number=i,due_date=today()-timedelta(days=5),total_paise=12345))
        db.commit()
    app=FastAPI();app.include_router(router);app.include_router(invoice_router);who={'id':'owner'};app.dependency_overrides[get_verified_identity]=lambda:who['id']
    def session():
        with Session(engine) as db:yield db
    app.dependency_overrides[get_saas_session]=session
    with TestClient(app) as client:yield client,who,engine
    engine.dispose()


BASE='/api/v1/organizations/a/contacts'
def preference(c,status='granted',**extra):return c.post(BASE+'/customers/buyer/preference',json={'channel':'email','status':status,'evidence':'Local consent evidence reference',**extra})
def preview(c,invoice='one',channel='email'):return c.post(BASE+'/preview',json={'invoice_id':invoice,'channel':channel})


def test_unknown_revoked_expired_consent_blocks_and_evidence_is_preserved(api):
    c,who,engine=api
    assert preview(c).json()['eligible'] is False
    assert preference(c).status_code==200
    draft=preview(c).json();assert draft['eligible'] is True and 'INR 123.45' in draft['draft'];assert draft['provider_connected'] is False
    with Session(engine) as db:assert db.scalar(select(func.count()).select_from(ContactRecord))==0
    assert preference(c,'revoked',evidence='Customer requested no email reminders').status_code==200
    assert preview(c).json()['draft'] is None
    detail=c.get(BASE+'/customers/buyer').json();assert len(detail['consent_changes'])==2;assert detail['preferences'][0]['status']=='revoked'
    assert preview(c,channel='whatsapp').json()['eligible'] is False
    with Session(engine) as db:
        p=db.scalar(select(ContactPreference));p.status='granted';p.expires_on=today()-timedelta(days=1);db.commit()
    assert any('expired' in r for r in preview(c).json()['reasons'])
    who['id']='accountant';assert preference(c).status_code==403;who['id']='viewer';assert preview(c).status_code==403;assert c.get(BASE+'/customers/buyer').status_code==200
    who['id']='bob';assert c.get(BASE+'/customers/buyer').status_code==403


def test_completed_external_contacts_are_replay_safe_and_cooldown_is_customer_wide(api):
    c,who,engine=api;preference(c)
    body={'invoice_id':'one','channel':'phone','contact_date':str(today()),'note':'Called customer outside CashPilot','request_key':'contact-1','confirmed_external_contact':True}
    assert c.post(BASE+'/records',json={**body,'confirmed_external_contact':False}).status_code==422
    first=c.post(BASE+'/records',json=body);assert first.status_code==201
    assert c.post(BASE+'/records',json=body).json()['id']==first.json()['id']
    assert c.post(BASE+'/records',json={**body,'note':'Different details'}).status_code==422
    blocked=preview(c,invoice='two').json();assert blocked['eligible'] is False and any('cooldown' in r for r in blocked['reasons'])
    plan=c.get('/api/v1/organizations/a/collections/plan').json();assert all(a['action']=='wait' for a in plan['actions'])
    with Session(engine) as db:assert db.scalar(select(func.count()).select_from(ContactRecord))==1


def test_disputes_promises_paid_and_future_invoices_block_drafts(api):
    c,who,engine=api;preference(c)
    with Session(engine) as db:
        create_promise(db,'a','one','owner',1000,today()+timedelta(days=1),'Expected receipt','promise-fixture');db.add(InvoiceDispute(organization_id='a',invoice_id='two',status='open',reason='delivery',description='Local issue'));db.commit()
    assert any('commitment' in r for r in preview(c).json()['reasons'])
    assert any('issue' in r for r in preview(c,'two').json()['reasons'])
    with Session(engine) as db:
        db.add(Payment(organization_id='a',invoice_id='one',amount_paise=12345,idempotency_key='settled'))
        db.get(Invoice,'two').due_date=today()+timedelta(days=2);db.commit()
    assert any('no outstanding' in r for r in preview(c).json()['reasons'])
    assert any('not due' in r for r in preview(c,'two').json()['reasons'])
