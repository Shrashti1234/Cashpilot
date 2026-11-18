from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from auth_identity import get_verified_identity
from operations import TradeDocument,StockMovement
from recurring import RecurringRule,advance,generate_due
from recurring_api import router
from saas_api import get_saas_session
from saas_domain import SaaSBase,Organization,Membership,Customer,Invoice


def test_month_end_keeps_original_anchor_and_weekly_intervals():
    feb=advance(date(2024,1,31),'monthly',1,31)
    assert feb==date(2024,2,29)
    assert advance(feb,'monthly',1,31)==date(2024,3,31)
    assert advance(date(2025,1,31),'monthly',1,31)==date(2025,2,28)
    assert advance(date(2026,1,1),'weekly',2,1)==date(2026,1,15)


def test_generation_is_bounded_repeatable_and_does_not_post_receivables_or_stock():
    engine=create_engine('sqlite://')
    SaaSBase.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Organization(id='a',name='A',mode='b2b'));db.flush()
        db.add_all([Membership(organization_id='a',user_id='owner',role='owner'),Customer(id='c',organization_id='a',name='Buyer')]);db.flush()
        template={'customer_id':'c','party':{'name':'Buyer'},'supplier':{'legal_name':'Seller'},'lines':[], 'totals':{'total_paise':10000},'notes':'Monthly service'}
        rule=RecurringRule(organization_id='a',name='Service',prefix='SRV',frequency='monthly',interval=1,anchor_day=31,
            next_date=date(2026,1,31),end_date=date(2026,4,30),terms_days=15,template=template,created_by='owner',sequence=1,active=True)
        db.add(rule);db.commit()
        first=generate_due(db,'a','owner',date(2026,3,31),limit=2);db.commit()
        assert len(first['created'])==2 and first['remaining_due']
        second=generate_due(db,'a','owner',date(2026,3,31));db.commit()
        assert len(second['created'])==1 and not second['remaining_due']
        assert generate_due(db,'a','owner',date(2026,3,31))['created']==[]
        docs=list(db.scalars(select(TradeDocument).order_by(TradeDocument.issue_date)))
        assert [d.issue_date for d in docs]==[date(2026,1,31),date(2026,2,28),date(2026,3,31)]
        assert [d.number for d in docs]==['SRV260131-0001','SRV260228-0002','SRV260331-0003']
        assert all(d.status=='draft' and d.invoice_id is None for d in docs)
        assert list(db.scalars(select(Invoice)))==[] and list(db.scalars(select(StockMovement)))==[]
        final=generate_due(db,'a','owner',date(2026,5,31));db.commit()
        assert len(final['created'])==1 and rule.active is False
        rule.next_date=date(2026,1,31);rule.sequence=1;rule.active=True;db.commit()
        conflict=generate_due(db,'a','owner',date(2026,1,31));db.commit()
        assert len(conflict['errors'])==1 and conflict['created']==[]
        assert rule.sequence==1 and rule.next_date==date(2026,1,31)
    engine.dispose()


def test_rule_management_is_tenant_scoped_and_paused_rules_do_not_generate():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool);SaaSBase.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([Organization(id='a',name='A',mode='b2b'),Organization(id='b',name='B',mode='b2b')]);db.flush()
        db.add_all([Membership(organization_id='a',user_id='owner',role='owner'),Membership(organization_id='a',user_id='viewer',role='viewer'),Membership(organization_id='b',user_id='bob',role='owner'),Customer(id='c',organization_id='a',name='Buyer')]);db.flush()
        db.add(TradeDocument(id='template',organization_id='a',kind='invoice',number='T-1',status='draft',customer_id='c',issue_date=date(2026,1,1),due_date=date(2026,1,31),party={'name':'Buyer'},supplier={},lines=[],totals={'total_paise':10000},received={},notes='',created_by='owner'));db.commit()
    app=FastAPI();app.include_router(router);who={'id':'owner'};app.dependency_overrides[get_verified_identity]=lambda:who['id']
    def session():
        with Session(engine) as db:yield db
    app.dependency_overrides[get_saas_session]=session
    base='/api/v1/organizations/a/operations/recurring'
    payload={'source_document_id':'template','name':'Monthly','prefix':'REC','frequency':'monthly','interval':1,'start_date':'2026-01-31','end_date':'2026-03-31','terms_days':30}
    with TestClient(app) as c:
        r=c.post(base,json=payload);assert r.status_code==201,r.text
        rid=r.json()['id']
        assert c.post(base+'/'+rid+'/active',json={'active':False}).status_code==200
        assert c.post(base+'/generate').json()['created']==[]
        who['id']='viewer';assert c.get(base).status_code==200
        assert c.post(base,json=payload).status_code==403 and c.post(base+'/generate').status_code==403
        who['id']='bob';assert c.get(base).status_code==403
        foreign='/api/v1/organizations/b/operations/recurring'
        assert c.post(foreign,json=payload).status_code==422
    engine.dispose()
