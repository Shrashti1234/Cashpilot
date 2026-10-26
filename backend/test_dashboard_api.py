from datetime import timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from auth_identity import get_verified_identity
from cash_ledger import CashEntry
from dashboard_api import router
from disputes import InvoiceDispute
from intelligence_api import today
from operations import Product,TradeDocument
from saas_api import get_saas_session
from saas_domain import SaaSBase,Organization,Membership,Customer,Invoice,InvoiceMemo,InvoiceRefund,Payment


def test_overview_reconciles_adjustments_refunds_cash_aging_and_tenant_boundaries():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool);SaaSBase.metadata.create_all(engine)
    now=today()
    with Session(engine) as db:
        db.add_all([Organization(id='a',name='A',mode='b2b'),Organization(id='b',name='B',mode='b2b')]);db.flush()
        db.add_all([Membership(organization_id='a',user_id='alice',role='owner'),Membership(organization_id='b',user_id='bob',role='owner'),Customer(id='ca',organization_id='a',name='Buyer'),Customer(id='cb',organization_id='b',name='Foreign buyer')]);db.flush()
        db.add_all([Invoice(id='i1',organization_id='a',customer_id='ca',invoice_number='I-1',due_date=now,total_paise=10000),Invoice(id='i2',organization_id='a',customer_id='ca',invoice_number='I-2',due_date=now-timedelta(days=1),total_paise=6000),Invoice(id='ib',organization_id='b',customer_id='cb',invoice_number='SECRET',due_date=now,total_paise=90000)]);db.flush()
        db.add_all([Payment(organization_id='a',invoice_id='i1',amount_paise=8000,idempotency_key='p1'),InvoiceMemo(organization_id='a',invoice_id='i1',kind='credit',number='C1',amount_paise=5000,reason='Agreed',actor_id='alice'),InvoiceRefund(organization_id='a',invoice_id='i1',amount_paise=1000,reason='Completed',idempotency_key='r1',actor_id='alice'),Payment(organization_id='b',invoice_id='ib',amount_paise=90000,idempotency_key='pb')])
        for direction,status,amount in [('out','actual',2000),('in','actual',500),('out','void',99000),('out','planned',45000)]:
            db.add(CashEntry(organization_id='a',entry_date=now,direction=direction,status=status,amount_paise=amount,description='Fixture'))
        db.add(Product(organization_id='a',sku='LOW',name='Low stock',unit='NOS',hsn_sac='',unit_price_paise=1000,tax_rate_bps=0,track_stock=True,reorder_milliunits=1000,active=True))
        db.add(TradeDocument(organization_id='a',kind='estimate',number='E1',status='draft',issue_date=now,due_date=now,party={},supplier={},lines=[],totals={},received={},notes='',created_by='alice'))
        db.add(InvoiceDispute(organization_id='a',invoice_id='i2',status='open',reason='quality',description='Review'));db.commit()
    app=FastAPI();app.include_router(router);who={'id':'alice'};app.dependency_overrides[get_verified_identity]=lambda:who['id']
    def session():
        with Session(engine) as db:yield db
    app.dependency_overrides[get_saas_session]=session
    with TestClient(app) as c:
        response=c.get('/api/v1/organizations/a/dashboard');assert response.status_code==200,response.text
        data=response.json();s=data['summary']
        assert s['customer_count']==1 and s['invoice_count']==2
        assert s['recorded_inflow_paise']==8500 and s['recorded_outflow_paise']==3000
        assert s['net_recorded_cash_paise']==5500 and s['customer_credit_paise']==2000
        assert s['outstanding_paise']==s['overdue_paise']==6000
        assert data['aging']['1_30']==6000 and sum(data['aging'].values())==6000
        assert data['top_customers'][0]['name']=='Buyer' and data['top_customers'][0]['share']==1
        assert s['low_stock_count']==s['open_disputes']==s['drafts_to_review']==1
        assert sum(m['amount_paise'] for m in data['operating_expenses_by_month'])==2000
        assert len(data['cash_activity'])==30 and len(data['operating_expenses_by_month'])==6
        assert 'Foreign buyer' not in response.text and 'SECRET' not in response.text
        assert c.get('/api/v1/organizations/b/dashboard').status_code==403
        with Session(engine) as db:db.get(Membership,('a','alice')).active=False;db.commit()
        assert c.get('/api/v1/organizations/a/dashboard').status_code==403
    engine.dispose()
