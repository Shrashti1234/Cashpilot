from datetime import datetime,timedelta,timezone
import hashlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from auth_identity import get_verified_identity
from organizations_api import router as organizations_router
from saas_api import get_saas_session,router as invoices_router
from saas_domain import SaaSBase,Organization,Membership
from teams import TeamInvitation
from teams_api import router


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr('request_limits._requests',{})
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool);SaaSBase.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([Organization(id='a',name='A',mode='b2b'),Organization(id='b',name='B',mode='b2b')]);db.flush()
        db.add_all([Membership(organization_id='a',user_id='owner',role='owner'),Membership(organization_id='a',user_id='admin',role='admin'),Membership(organization_id='a',user_id='viewer',role='viewer'),Membership(organization_id='b',user_id='bob',role='owner')]);db.commit()
    app=FastAPI();app.include_router(router);app.include_router(organizations_router);app.include_router(invoices_router)
    user={'id':'owner'};app.dependency_overrides[get_verified_identity]=lambda:user['id']
    def session():
        with Session(engine) as db:yield db
    app.dependency_overrides[get_saas_session]=session
    with TestClient(app) as c:yield c,user,engine
    engine.dispose()


BASE='/api/v1/organizations/a/team'


def test_private_invitation_is_hashed_account_bound_and_idempotent(api):
    c,user,engine=api
    r=c.post(BASE+'/invitations',json={'target_user_id':'recipient','role':'accountant'});assert r.status_code==201,r.text
    token=r.json()['token'];iid=r.json()['id']
    with Session(engine) as db:
        stored=db.get(TeamInvitation,iid)
        assert stored.token_hash==hashlib.sha256(token.encode()).hexdigest()
        assert token not in str(stored.__dict__)
    assert 'token' not in c.get(BASE).json()['invitations'][0]
    user['id']='bob';assert c.post('/api/v1/invitations/accept',json={'token':token}).status_code==403
    user['id']='recipient'
    accepted=c.post('/api/v1/invitations/accept',json={'token':token});assert accepted.status_code==200,accepted.text
    assert accepted.json()['organization']['role']=='accountant'
    assert c.post('/api/v1/invitations/accept',json={'token':token}).status_code==200
    assert c.get('/api/v1/organizations').json()['organizations'][0]['id']=='a'
    user['id']='owner'
    assert len([m for m in c.get(BASE).json()['members'] if m['user_id']=='recipient'])==1


def test_last_owner_and_admin_escalation_are_rejected(api):
    c,user,_=api
    assert c.post(BASE+'/member',json={'user_id':'owner','role':'admin','active':True}).status_code==422
    assert c.post(BASE+'/member',json={'user_id':'owner','role':'owner','active':False}).status_code==422
    user['id']='admin'
    assert c.post(BASE+'/member',json={'user_id':'viewer','role':'owner','active':True}).status_code==403
    assert c.post(BASE+'/member',json={'user_id':'owner','role':'viewer','active':False}).status_code==403
    assert c.post(BASE+'/invitations',json={'target_user_id':'new-admin','role':'admin'}).status_code==403
    user['id']='owner'
    assert c.post(BASE+'/member',json={'user_id':'admin','role':'owner','active':True}).status_code==200
    assert c.post(BASE+'/member',json={'user_id':'owner','role':'admin','active':True}).status_code==200


def test_revocation_removes_existing_api_access_and_old_invite_cannot_restore_it(api):
    c,user,_=api
    invite=c.post(BASE+'/invitations',json={'target_user_id':'recipient','role':'viewer'}).json()
    user['id']='recipient';assert c.post('/api/v1/invitations/accept',json={'token':invite['token']}).status_code==200
    assert c.get('/api/v1/organizations/a/customers').status_code==200
    user['id']='owner';assert c.post(BASE+'/member',json={'user_id':'recipient','role':'viewer','active':False}).status_code==200
    user['id']='recipient'
    assert c.get('/api/v1/organizations/a/customers').status_code==403
    assert c.get('/api/v1/organizations').json()['organizations']==[]
    assert c.post('/api/v1/invitations/accept',json={'token':invite['token']}).status_code==403


def test_expiry_revocation_foreign_tenant_and_changed_inviter_permissions(api):
    c,user,engine=api
    first=c.post(BASE+'/invitations',json={'target_user_id':'expired','role':'viewer'}).json()
    revoked=c.post(BASE+'/invitations',json={'target_user_id':'revoked','role':'viewer'}).json()
    changed=c.post(BASE+'/invitations',json={'target_user_id':'new-admin','role':'admin'}).json()
    assert c.post(BASE+'/invitations/'+revoked['id']+'/revoke').status_code==200
    with Session(engine) as db:
        db.get(TeamInvitation,first['id']).expires_at=datetime.now(timezone.utc)-timedelta(seconds=1);db.commit()
    user['id']='expired';assert c.post('/api/v1/invitations/accept',json={'token':first['token']}).status_code==404
    user['id']='revoked';assert c.post('/api/v1/invitations/accept',json={'token':revoked['token']}).status_code==404
    user['id']='bob';assert c.get(BASE).status_code==403
    user['id']='owner';assert c.post(BASE+'/member',json={'user_id':'admin','role':'owner','active':True}).status_code==200
    assert c.post(BASE+'/member',json={'user_id':'owner','role':'admin','active':True}).status_code==200
    user['id']='new-admin';assert c.post('/api/v1/invitations/accept',json={'token':changed['token']}).status_code==403
