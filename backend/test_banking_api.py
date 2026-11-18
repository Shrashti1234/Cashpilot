from datetime import timedelta
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,select,func
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from auth_identity import get_verified_identity
from banking import BankTransaction,BankMatch,parse_statement
from banking_api import router
from cash_ledger import CashEntry
from intelligence_api import today,router as intelligence_router
from saas_api import get_saas_session
from saas_domain import SaaSBase,Organization,Membership,Customer,Invoice,Payment,InvoiceRefund


@pytest.fixture
def api():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool);SaaSBase.metadata.create_all(engine)
    with Session(engine) as db:
        for org,user in [('a','owner'),('b','bob')]:
            db.add(Organization(id=org,name=org,mode='b2b'));db.flush();db.add(Membership(organization_id=org,user_id=user,role='owner'));db.add(Customer(id='c'+org,organization_id=org,name='Buyer'));db.flush();db.add(Invoice(id='i'+org,organization_id=org,customer_id='c'+org,invoice_number='INV',due_date=today(),total_paise=10000));db.flush();db.add(Payment(id='p'+org,organization_id=org,invoice_id='i'+org,amount_paise=5000,idempotency_key='pay'))
        db.add(Membership(organization_id='a',user_id='viewer',role='viewer'));db.add(CashEntry(id='expense',organization_id='a',entry_date=today(),amount_paise=1234,status='actual',direction='out',description='Operating expense'));db.add(CashEntry(id='plan',organization_id='a',entry_date=today(),amount_paise=1234,status='planned',direction='out',description='Planned expense'));db.add(InvoiceRefund(id='refund',organization_id='a',invoice_id='ia',amount_paise=500,idempotency_key='refund',reason='Completed refund',actor_id='owner'));db.commit()
    app=FastAPI();app.include_router(router);app.include_router(intelligence_router);who={'id':'owner'};app.dependency_overrides[get_verified_identity]=lambda:who['id']
    def session():
        with Session(engine) as db:yield db
    app.dependency_overrides[get_saas_session]=session
    with TestClient(app) as client:yield client,who,engine
    engine.dispose()


BASE='/api/v1/organizations/a/banking'
def statement(*rows):return 'booked_date,reference,description,amount_inr,currency\n'+'\n'.join(f'{today()},{ref},{desc},{amount},INR' for ref,desc,amount in rows)
def account(c):return c.post(BASE+'/accounts',json={'label':'Local checking alias'}).json()['id']
def load(c,acct,*rows):return c.post(BASE+'/accounts/'+acct+'/import',json={'csv_text':statement(*rows)})
def rows(c,acct):return c.get(BASE+'/accounts/'+acct+'/transactions').json()['rows']
def match(c,tx,kind,target,**extra):return c.post(BASE+'/transactions/'+tx+'/match',json={'kind':kind,'target_id':target,'note':'Reference and date reviewed','confirmed':True,**extra})


def test_import_is_exact_deduplicated_atomic_and_not_a_receipt(api):
    c,who,engine=api;acct=account(c);content=statement(('BANK-1','Customer receipt','50.00'),('BANK-2','Expense','-12.34'))
    preview=c.post(BASE+'/accounts/'+acct+'/preview',json={'csv_text':content});assert preview.status_code==200;assert preview.json()['new_net_change_paise']==3766
    with Session(engine) as db:assert db.scalar(select(func.count()).select_from(BankTransaction))==0
    result=load(c,acct,('BANK-1','Customer receipt','50.00'),('BANK-2','Expense','-12.34'));assert result.json()=={'imported':2,'duplicates':0}
    assert load(c,acct,('BANK-1','Customer receipt','50.00')).json()=={'imported':0,'duplicates':1}
    failed=load(c,acct,('BANK-3','New','1.00'),('BANK-1','Changed amount','60.00'));assert failed.status_code==422
    assert len(rows(c,acct))==2
    with Session(engine) as db:assert db.scalar(select(func.count()).select_from(Payment).where(Payment.organization_id=='a'))==1
    who['id']='bob';assert c.get(BASE+'/accounts/'+acct+'/transactions').status_code==403
    who['id']='viewer';assert c.get(BASE+'/accounts/'+acct+'/transactions').status_code==200;assert load(c,acct,('X','Blocked','1.00')).status_code==403


def test_reconciliation_is_one_to_one_reversible_and_tenant_scoped(api):
    c,who,engine=api;acct=account(c);load(c,acct,('A','Receipt','50.00'),('B','Other receipt','50.00'),('C','Wrong amount','49.00'))
    tx={r['reference']:r['id'] for r in rows(c,acct)}
    candidates=c.get(BASE+'/transactions/'+tx['A']+'/candidates').json()['candidates'];assert [r['id'] for r in candidates]==['pa']
    assert match(c,tx['A'],'payment','pb').status_code==422
    assert match(c,tx['A'],'payment','pa',confirmed=False).status_code==422
    first=match(c,tx['A'],'payment','pa');assert first.status_code==201
    assert match(c,tx['A'],'payment','pa').json()['id']==first.json()['id']
    assert match(c,tx['B'],'payment','pa').status_code==422
    assert match(c,tx['C'],'payment','pa').status_code==422
    assert c.post(BASE+'/transactions/'+tx['A']+'/reverse',json={'reason':'Selected wrong statement row'}).status_code==200
    assert match(c,tx['B'],'payment','pa').status_code==201
    history=c.get(BASE+'/transactions/'+tx['A']+'/history').json()['matches'];assert history[0]['active'] is False and history[0]['reversal_reason']=='Selected wrong statement row'
    with Session(engine) as db:assert db.scalar(select(func.count()).select_from(BankMatch))==2;assert db.get(Payment,'pa').amount_paise==5000


def test_statement_search_and_match_filter_apply_before_pagination(api):
    c,_,_=api
    acct=account(c)
    assert load(c,acct,*(('B%02d'%i,'Incoming receipt','50.00') for i in range(30))).status_code==201
    path=BASE+'/accounts/'+acct+'/transactions'
    first=c.get(path,params={'page_size':10}).json()
    last=c.get(path,params={'page_size':10,'page':3}).json()
    assert first['total']==last['total']==30 and len(last['rows'])==10
    assert not {r['id'] for r in first['rows']} & {r['id'] for r in last['rows']}
    tx=last['rows'][0]
    assert match(c,tx['id'],'payment','pa').status_code==201
    matched=c.get(path,params={'view':'matched','q':tx['reference'],'page_size':1}).json()
    assert matched['total']==1 and matched['rows'][0]['id']==tx['id']
    assert matched['summary']['row_count']==30 and matched['summary']['matched_count']==1
    assert c.get(path,params={'view':'unmatched'}).json()['total']==29
    assert c.get(path,params={'q':'%'}).json()['total']==0


def test_only_actual_direction_matched_records_are_reconciled_and_locked(api):
    c,who,engine=api;acct=account(c);load(c,acct,('E','Expense','-12.34'),('F','Refund','-5.00'),('G','Wrong direction','12.34'))
    tx={r['reference']:r['id'] for r in rows(c,acct)}
    assert match(c,tx['E'],'cash_entry','plan').status_code==422
    assert match(c,tx['G'],'cash_entry','expense').status_code==422
    assert match(c,tx['E'],'cash_entry','expense').status_code==201
    update={'entry_date':str(today()),'direction':'out','status':'void','amount_paise':1234,'description':'Voided'}
    assert c.post('/api/v1/organizations/a/cash-entries/expense',json=update).status_code==409
    assert match(c,tx['F'],'refund','refund').status_code==201
    assert c.post(BASE+'/transactions/'+tx['E']+'/reverse',json={'reason':'Review correction'}).status_code==200
    assert c.post('/api/v1/organizations/a/cash-entries/expense',json=update).status_code==200


@pytest.mark.parametrize('content',[
    'date,reference,description,amount_inr,currency\n2026-01-01,A,X,1.00,INR',
    statement(('A','X','1.001')),statement(('A','X','1e3')),statement(('A','X','0.00')),
    statement(('A','X','1.00'),('A','Y','2.00')),
    f'booked_date,reference,description,amount_inr,currency\n{today()+timedelta(days=1)},A,X,1.00,INR',
    f'booked_date,reference,description,amount_inr,currency\n{today()},A,X,1.00,USD',
])
def test_rejects_ambiguous_statement_data(content):
    with pytest.raises(ValueError):parse_statement(content,today())
