"""Opt-in, loopback-only PostgreSQL checks. Never runs against hosted databases."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import os
from pathlib import Path
import subprocess
from threading import Barrier,Event
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine,delete,func,select,text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

import audit,disputes,cash_ledger,recurring,teams,buyer_access,promises  # register all dependent tables
import banking
import contacts
import forecast_journal
import financial_approvals
import collection_tasks
from finance_api import RefundInput,add_refund
from intelligence_api import today
from operations import BusinessProfile,Product,StockMovement,TradeDocument,post_stock,stock_balance
from operations_api import DocumentInput,IssueInput,add_document,issue_document
from saas_domain import SaaSBase,Organization,Membership,Customer,Invoice,InvoiceMemo,InvoiceRefund,Payment,create_invoice,invoice_positions,record_payment
from teams_api import locked_admin
from audit import record_event

ADMIN=os.getenv('CASH_PILOT_PG_ADMIN_URL')
RUNTIME=os.getenv('CASH_PILOT_PG_RUNTIME_URL')
pytestmark=pytest.mark.skipif(not (ADMIN and RUNTIME),reason='Opt-in local PostgreSQL fixture is not configured')


@pytest.fixture
def pg():
    for raw in (ADMIN,RUNTIME):
        url=make_url(raw)
        if url.host not in {'127.0.0.1','localhost'} or url.database!='cashpilot_checks':
            pytest.fail('Refusing PostgreSQL checks outside the dedicated loopback fixture')
    admin=create_engine(ADMIN,hide_parameters=True,pool_pre_ping=True)
    runtime=create_engine(RUNTIME,hide_parameters=True,pool_pre_ping=True,pool_size=5,max_overflow=0,
                          connect_args={'options':'-c lock_timeout=5000 -c statement_timeout=15000'})
    with admin.connect() as connection:
        if not connection.execute(text("SELECT 1 FROM cashpilot_local_test_marker WHERE marker='cashpilot-local-postgres-isolated-20261026'")).scalar():
            pytest.fail('Missing isolated database marker')
    org,user,customer,product=(str(uuid4()) for _ in range(4))
    try:
        with Session(runtime) as db:
            db.add(Organization(id=org,name='PostgreSQL local fixture',mode='b2b'));db.flush()
            db.add(Membership(organization_id=org,user_id=user,role='owner',active=True))
            db.add(Customer(id=customer,organization_id=org,name='Synthetic fixture buyer'))
            db.add(BusinessProfile(organization_id=org,legal_name='Fixture seller',address='Local fixture',gstin='',state_code='27',require_approval=False))
            db.add(Product(id=product,organization_id=org,sku='PG-ITEM',name='Fixture product',unit='NOS',hsn_sac='',unit_price_paise=10000,tax_rate_bps=0,track_stock=True,reorder_milliunits=0,active=True));db.commit()
        yield {'admin':admin,'runtime':runtime,'org':org,'user':user,'customer':customer,'product':product}
    finally:
        runtime.dispose()
        with admin.begin() as connection:
            # IDs are generated above, and the database is guarded before any
            # mutation. Cleanup touches only this fixture's organization.
            for table in reversed(SaaSBase.metadata.sorted_tables):
                if 'organization_id' in table.c:connection.execute(delete(table).where(table.c.organization_id==org))
            connection.execute(delete(Organization).where(Organization.id==org))
        admin.dispose()


def new_invoice(pg,number='PG-INV'):
    with Session(pg['runtime'],expire_on_commit=False) as db:
        row=create_invoice(db,user_id=pg['user'],organization_id=pg['org'],customer_id=pg['customer'],
                           invoice_number=number,due_date=today(),total_paise=10000)
        db.commit();return row.id


def test_runtime_import_and_follow_up_flow(pg):
    from receivable_import_api import MappedInput, CommitInput, preview, commit
    from collection_worklist_api import Assignment, assign, worklist
    org, actor = pg['org'], pg['user']
    file = MappedInput(content='customer,reference,due,amount\nSynthetic fixture buyer,PILOT-1,2026-10-01,25.55',
                       columns={'customer':'customer','reference':'reference','due':'due','amount':'amount'})
    with Session(pg['runtime']) as db:
        plan = preview(org, file, actor, db)
        assert commit(org, CommitInput(**file.model_dump(), preview_digest=plan['preview_digest']), actor, db)['imported'] == 1
        row = worklist(org, actor, db)['actions'][0]
        assert row['outstanding_paise'] == 2555
        assign(org, row['invoice_id'], Assignment(assignee=actor, follow_up=today()), actor, db)
        assert worklist(org, actor, db)['actions'][0]['task']['assignee'] == actor


def parallel(function):
    barrier=Barrier(2)
    def invoke(index):barrier.wait(timeout=10);return function(index)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(invoke,i) for i in range(2)]
        return [f.result(timeout=25) for f in futures]


def test_postgres_serializes_stock_deductions_without_overselling(pg):
    with Session(pg['runtime']) as db:
        post_stock(db,organization_id=pg['org'],product_id=pg['product'],quantity=1000,reason='opening',reference='Fixture opening',request_key='opening',actor_id=pg['user']);db.commit()
    def sell(index):
        with Session(pg['runtime']) as db:
            try:
                post_stock(db,organization_id=pg['org'],product_id=pg['product'],quantity=-1000,reason='invoice_issue',reference='Fixture sale',request_key=f'sale-{index}',actor_id=pg['user']);db.commit();return 'posted'
            except ValueError:db.rollback();return 'rejected'
    assert sorted(parallel(sell))==['posted','rejected']
    with Session(pg['runtime']) as db:assert stock_balance(db,pg['org'],pg['product'])==0


def test_postgres_duplicate_payment_requests_return_one_posted_receipt(pg):
    inv=new_invoice(pg)
    def pay(_):
        with Session(pg['runtime'],expire_on_commit=False) as db:
            p=record_payment(db,user_id=pg['user'],organization_id=pg['org'],invoice_id=inv,amount_paise=6000,idempotency_key='concurrent-payment');db.commit();return p.id
    ids=parallel(pay);assert ids[0]==ids[1]
    with Session(pg['runtime']) as db:
        assert db.scalar(select(func.count()).select_from(Payment).where(Payment.organization_id==pg['org']))==1
        assert invoice_positions(db,pg['org'],[db.get(Invoice,inv)])[inv]['outstanding_paise']==4000


def test_postgres_bank_matches_preserve_evidence_and_serialize_competing_rows(pg):
    from banking_api import AccountInput,StatementInput,MatchInput,add_account,import_statement,reconcile
    inv=new_invoice(pg)
    with Session(pg['runtime'],expire_on_commit=False) as db:
        receipt=record_payment(db,user_id=pg['user'],organization_id=pg['org'],invoice_id=inv,amount_paise=5000,idempotency_key='bank-fixture');db.commit();receipt_id=receipt.id
        acct=add_account(pg['org'],AccountInput(label='Local bank fixture'),pg['user'],db)['id']
        csv_text=f'booked_date,reference,description,amount_inr,currency\n{today()},A,Fixture credit,50.00,INR\n{today()},B,Other fixture credit,50.00,INR'
        assert import_statement(pg['org'],acct,StatementInput(csv_text=csv_text),pg['user'],db)['imported']==2
        txs=list(db.scalars(select(banking.BankTransaction.id).where(banking.BankTransaction.organization_id==pg['org'])))
        assert not db.scalar(text("SELECT has_table_privilege(current_user,'saas_bank_transactions','UPDATE') OR has_table_privilege(current_user,'saas_bank_transactions','DELETE')"))
    def match(index):
        with Session(pg['runtime']) as db:
            try:reconcile(pg['org'],txs[index],MatchInput(kind='payment',target_id=receipt_id,note='Synthetic reference review',confirmed=True),pg['user'],db);return 'matched'
            except HTTPException as exc:assert exc.status_code in {409,422};return 'rejected'
    assert sorted(parallel(match))==['matched','rejected']
    with Session(pg['runtime']) as db:assert db.scalar(select(func.count()).select_from(banking.BankMatch).where(banking.BankMatch.organization_id==pg['org']))==1


def test_postgres_contact_history_is_append_only_and_controls_drafts(pg):
    from contacts_api import PreferenceInput,RecordInput,PreviewInput,save_preference,record_contact,reminder_preview
    inv=new_invoice(pg)
    with Session(pg['runtime']) as db:
        save_preference(pg['org'],pg['customer'],PreferenceInput(channel='email',status='granted',evidence='Synthetic local consent evidence'),pg['user'],db)
        assert reminder_preview(pg['org'],PreviewInput(invoice_id=inv,channel='email'),pg['user'],db)['eligible'] is True
        payload=RecordInput(invoice_id=inv,channel='email',contact_date=today(),note='Synthetic external contact record',request_key='contact-fixture',confirmed_external_contact=True)
        first=record_contact(pg['org'],payload,pg['user'],db)
        assert record_contact(pg['org'],payload,pg['user'],db)['id']==first['id']
        assert reminder_preview(pg['org'],PreviewInput(invoice_id=inv,channel='email'),pg['user'],db)['eligible'] is False
        assert not db.scalar(text("SELECT has_table_privilege(current_user,'saas_contact_records','UPDATE') OR has_table_privilege(current_user,'saas_contact_consent_changes','DELETE')"))


def test_postgres_forecast_snapshots_are_replay_safe_and_immutable(pg):
    with Session(pg['runtime']) as db:
        first=forecast_journal.create_snapshot(db,pg['org'],pg['user'],today(),'snapshot-fixture');db.commit();snapshot_id=first.id
        replay=forecast_journal.create_snapshot(db,pg['org'],pg['user'],today(),'snapshot-fixture');db.commit();assert replay.id==snapshot_id
        assert first.payload['expense_method']=='no_expense_history'
        assert not db.scalar(text("SELECT has_table_privilege(current_user,'saas_forecast_snapshots','UPDATE') OR has_table_privilege(current_user,'saas_forecast_reviews','DELETE')"))


def test_postgres_invoice_bundle_uses_restricted_runtime_permissions(pg):
    from evidence import invoice_packet,make_bundle
    from zipfile import ZipFile
    from io import BytesIO
    import json
    inv=new_invoice(pg)
    with Session(pg['runtime']) as db:
        packet=invoice_packet(db,pg['org'],inv,pg['user']);bundle=make_bundle(packet,pg['org'],inv);db.commit()
        with ZipFile(BytesIO(bundle)) as archive:
            assert json.loads(archive.read('ledger.json'))['outstanding_paise']==10000


def test_postgres_financial_approval_posts_once_with_immutable_request_payload(pg):
    from financial_approvals_api import PolicyInput,RequestInput,DecisionInput,set_policy,request_approval,decide
    reviewer=str(uuid4());inv=new_invoice(pg)
    with Session(pg['runtime']) as db:
        db.add(Membership(organization_id=pg['org'],user_id=reviewer,role='admin',active=True));db.commit()
        set_policy(pg['org'],PolicyInput(require_approval=True),pg['user'],db)
        row=request_approval(pg['org'],RequestInput(invoice_id=inv,operation='memo',memo={'kind':'credit','number':'PG-APPROVAL','amount_paise':1000,'reason':'Synthetic independent review'},request_key='approval-fixture'),pg['user'],db);rid=row['id']
        assert not db.scalar(text("SELECT has_column_privilege(current_user,'saas_financial_approvals','payload','UPDATE') OR has_column_privilege(current_user,'saas_financial_approvals','requested_by','UPDATE')"))
    def approve(_):
        with Session(pg['runtime']) as db:return decide(pg['org'],rid,DecisionInput(decision='approve',note='Reviewed synthetic fixture'),reviewer,db)['posted_id']
    ids=parallel(approve);assert ids[0]==ids[1]
    with Session(pg['runtime']) as db:
        assert db.scalar(select(func.count()).select_from(InvoiceMemo).where(InvoiceMemo.organization_id==pg['org']))==1
        assert invoice_positions(db,pg['org'],[db.get(Invoice,inv)])[inv]['outstanding_paise']==9000


def test_postgres_source_tax_snapshots_remain_immutable_through_approval_and_issue(pg):
    from operations_api import approve_document
    from tax_register_api import tax_register
    reviewer=str(uuid4())
    with Session(pg['runtime']) as db:
        db.add(Membership(organization_id=pg['org'],user_id=reviewer,role='admin',active=True));profile=db.get(BusinessProfile,pg['org']);profile.require_approval=True;profile.gstin='27ABCDE1234F1Z5';db.commit()
        payload=DocumentInput(kind='invoice',number='PG-TAX',customer_id=pg['customer'],issue_date=today(),due_date=today(),party={'name':'Synthetic buyer','address':'Fixture address','state_code':'27','place_of_supply':'27','gstin':''},lines=[{'description':'Synthetic service','hsn_sac':'998313','unit':'NOS','quantity_milliunits':1000,'unit_price_paise':10000,'discount_paise':0,'tax_rate_bps':1800,'cess_rate_bps':0}])
        doc=add_document(pg['org'],payload,pg['user'],db)
        approve_document(pg['org'],doc['id'],reviewer,db)
        issue_document(pg['org'],doc['id'],IssueInput(tax_reviewed=True),pg['user'],db)
        report=tax_register(pg['org'],today(),today(),pg['user'],db,None);assert report['totals']['total_paise']==11800 and report['totals']['sgst_paise']==900
        assert not db.scalar(text("SELECT has_column_privilege(current_user,'saas_trade_documents','lines','UPDATE') OR has_column_privilege(current_user,'saas_trade_documents','supplier','UPDATE') OR has_column_privilege(current_user,'saas_trade_documents','issue_date','UPDATE')"))
        assert db.scalar(text("SELECT has_column_privilege(current_user,'saas_trade_documents','status','UPDATE')"))


def test_postgres_concurrent_refunds_cannot_spend_the_same_customer_credit(pg):
    inv=new_invoice(pg)
    with Session(pg['runtime']) as db:
        record_payment(db,user_id=pg['user'],organization_id=pg['org'],invoice_id=inv,amount_paise=8000,idempotency_key='receipt')
        db.add(InvoiceMemo(organization_id=pg['org'],invoice_id=inv,kind='credit',number='PG-CR',amount_paise=5000,reason='Fixture reduction',actor_id=pg['user']));db.commit()
    def refund(index):
        with Session(pg['runtime']) as db:
            try:
                add_refund(pg['org'],inv,RefundInput(amount_paise=2000,reason='External fixture transfer completed',idempotency_key=f'refund-{index}',confirmed_external_refund=True),pg['user'],db)
                return 'recorded'
            except HTTPException as error:
                assert error.status_code==422;return 'rejected'
    assert sorted(parallel(refund))==['recorded','rejected']
    with Session(pg['runtime']) as db:
        pos=invoice_positions(db,pg['org'],[db.get(Invoice,inv)])[inv]
        assert pos['refunded_paise']==2000 and pos['credit_balance_paise']==1000


def test_postgres_failed_invoice_issue_rolls_back_its_receivable(pg):
    with Session(pg['runtime']) as db:
        post_stock(db,organization_id=pg['org'],product_id=pg['product'],quantity=1000,reason='opening',reference='Fixture opening',request_key='opening',actor_id=pg['user']);db.commit()
        ids=[]
        for n in range(2):
            payload=DocumentInput(kind='invoice',number=f'PG-SALE-{n}',customer_id=pg['customer'],issue_date=today(),due_date=today(),
                party={'name':'Fixture buyer','address':'Local address','gstin':'','state_code':'27','place_of_supply':'27'},
                lines=[{'product_id':pg['product'],'description':'Fixture product','hsn_sac':'','unit':'NOS','quantity_milliunits':1000,'unit_price_paise':10000,'discount_paise':0,'tax_rate_bps':0,'cess_rate_bps':0}])
            ids.append(add_document(pg['org'],payload,pg['user'],db)['id'])
    def issue(index):
        with Session(pg['runtime']) as db:
            try:issue_document(pg['org'],ids[index],IssueInput(tax_reviewed=True),pg['user'],db);return 'issued'
            except HTTPException as error:assert error.status_code==422;return 'rejected'
    assert sorted(parallel(issue))==['issued','rejected']
    with Session(pg['runtime']) as db:
        assert db.scalar(select(func.count()).select_from(Invoice).where(Invoice.organization_id==pg['org']))==1
        docs=list(db.scalars(select(TradeDocument).where(TradeDocument.organization_id==pg['org'])))
        assert sorted(d.status for d in docs)==['draft','issued']
        assert stock_balance(db,pg['org'],pg['product'])==0


def test_postgres_runtime_and_browser_database_privileges_remain_restricted(pg):
    with pg['admin'].connect() as connection:
        role=connection.execute(text("SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls,rolinherit,rolconnlimit FROM pg_roles WHERE rolname='cashpilot_backend'")).one()
        assert not any(role[:6]) and role.rolconnlimit==10
        rows=list(connection.execute(text("SELECT relname,relrowsecurity FROM pg_class WHERE relnamespace='public'::regnamespace AND relkind='r' AND relname LIKE 'saas_%'")))
        assert all(row.relrowsecurity for row in rows)
        assert not connection.execute(text("SELECT pg_has_role('anon','cashpilot_backend','MEMBER') OR pg_has_role('authenticated','cashpilot_backend','MEMBER')")).scalar()
        for row in rows:
            assert not connection.execute(text("SELECT has_table_privilege('anon',:name,'SELECT') OR has_table_privilege('authenticated',:name,'SELECT')"),{'name':row.relname}).scalar()
    for statement in ["UPDATE saas_audit_events SET action='tampered' WHERE 1=0",'DELETE FROM saas_invoices WHERE 1=0','DELETE FROM saas_stock_movements WHERE 1=0','UPDATE saas_invoice_refunds SET amount_paise=1 WHERE 1=0']:
        with pytest.raises(ProgrammingError) as rejected:
            with pg['runtime'].begin() as connection:connection.execute(text(statement))
        assert rejected.value.orig.sqlstate=='42501'


def test_postgres_team_lock_does_not_block_unrelated_audit_foreign_key_inserts(pg):
    locked,inserted=Event(),Event()
    def controller():
        with Session(pg['runtime']) as db:
            locked_admin(db,pg['user'],pg['org']);locked.set()
            assert inserted.wait(timeout=8),'Team control lock blocked a normal audit insert'
            db.rollback()
    def writer():
        assert locked.wait(timeout=8)
        with Session(pg['runtime']) as db:
            record_event(db,pg['org'],pg['user'],'fixture.concurrent_audit','fixture')
            db.commit();inserted.set()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(controller),pool.submit(writer)]
        for future in futures:future.result(timeout=20)


def test_postgres_backup_restores_balances_unicode_audit_and_permissions(pg,tmp_path):
    binaries=os.getenv('CASH_PILOT_PG_BIN_DIR')
    if not binaries:pytest.skip('Matching pg_dump/pg_restore tools are not configured')
    extension='.exe' if os.name=='nt' else ''
    dump=Path(binaries)/('pg_dump'+extension);restore=Path(binaries)/('pg_restore'+extension)
    if not dump.is_file() or not restore.is_file():pytest.skip('PostgreSQL client tools are unavailable')
    inv=new_invoice(pg)
    with Session(pg['runtime']) as db:
        db.get(Invoice,inv).total_paise=12345
        db.get(Customer,pg['customer']).name='स्थानीय ग्राहक'
        record_payment(db,user_id=pg['user'],organization_id=pg['org'],invoice_id=inv,amount_paise=2345,idempotency_key='backup-receipt')
        db.add(InvoiceMemo(organization_id=pg['org'],invoice_id=inv,kind='credit',number='BACKUP-CR',amount_paise=1000,reason='Synthetic backup fixture',actor_id=pg['user']))
        record_event(db,pg['org'],pg['user'],'fixture.backup','fixture');db.commit()
    with pg['admin'].connect() as connection:
        if connection.execute(select(func.count()).select_from(Organization)).scalar()!=1:
            pytest.fail('Refusing full backup with non-fixture organizations present')
        revision=connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
    target='cashpilot_checks_restore_'+uuid4().hex[:12]
    admin_url=make_url(ADMIN);env=os.environ.copy()
    if admin_url.password:env['PGPASSWORD']=admin_url.password
    else:env.pop('PGPASSWORD',None)
    common=['--host',admin_url.host,'--port',str(admin_url.port or 5432),'--username',admin_url.username,'--no-password']
    archive=tmp_path/'synthetic-fixture.dump'
    def invoke(command):
        result=subprocess.run([str(p) for p in command],env=env,capture_output=True,text=True,timeout=60,
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        stderr=result.stderr.replace(admin_url.password,'[REDACTED]') if admin_url.password else result.stderr
        assert result.returncode==0,stderr
    invoke([dump,*common,'--format=custom','--dbname',admin_url.database,'--file',archive])
    control=create_engine(admin_url.set(database='postgres'),isolation_level='AUTOCOMMIT',hide_parameters=True)
    target_created=False;restored_admin=None;restored_runtime=None
    try:
        # Name is generated here, never supplied by a caller or environment.
        with control.connect() as connection:connection.exec_driver_sql(f'CREATE DATABASE "{target}"')
        target_created=True
        invoke([restore,*common,'--exit-on-error','--dbname',target,archive])
        restored_admin=create_engine(admin_url.set(database=target),hide_parameters=True)
        restored_runtime=create_engine(make_url(RUNTIME).set(database=target),hide_parameters=True)
        with Session(restored_runtime) as db:
            restored=db.get(Invoice,inv)
            assert invoice_positions(db,pg['org'],[restored])[inv]['outstanding_paise']==9000
            assert db.get(Customer,pg['customer']).name=='स्थानीय ग्राहक'
            assert db.scalar(select(func.count()).select_from(audit.AuditEvent).where(audit.AuditEvent.organization_id==pg['org']))==1
        with restored_admin.connect() as connection:
            assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one()==revision
            assert not connection.execute(text("SELECT has_table_privilege('anon','saas_invoices','SELECT') OR has_table_privilege('cashpilot_backend','saas_audit_events','UPDATE')")).scalar()
            assert connection.execute(text("SELECT bool_and(relrowsecurity) FROM pg_class WHERE relnamespace='public'::regnamespace AND relkind='r' AND relname LIKE 'saas_%'")).scalar()
    finally:
        if restored_admin:restored_admin.dispose()
        if restored_runtime:restored_runtime.dispose()
        if target_created:
            with control.connect() as connection:connection.exec_driver_sql(f'DROP DATABASE "{target}" WITH (FORCE)')
        control.dispose()
