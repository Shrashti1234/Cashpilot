from datetime import timedelta
from sqlalchemy.orm import Session
from test_operations import api,setup,draft,BASE
from operations import TradeDocument
from intelligence_api import today
from tax_register_api import router
from saas_domain import Invoice,InvoiceMemo


def issue(c,product,number='TAX-1'):
    doc,_=draft(c,product,number=number,quantity=1000)
    # Non-stock services are used here so this tax test does not also require
    # a stock-opening workflow already covered by operations tests.
    result=c.post(BASE+'/documents/'+doc['id']+'/issue',json={'tax_reviewed':True});assert result.status_code==200,result.text
    return result.json()


def test_register_uses_only_issued_snapshots_and_preserves_tax_after_financial_memos(api):
    c,who,engine=api;c.app.include_router(router);product=setup(c)
    c.post(BASE+'/products/'+product,json={'sku':'SKU-1','name':'Service','unit':'NOS','hsn_sac':'8471','unit_price_paise':10000,'tax_rate_bps':1800,'track_stock':False,'reorder_milliunits':0,'active':True})
    doc=issue(c,product);draft(c,product,kind='estimate',number='ESTIMATE');draft(c,product,number='UNISSUED')
    with Session(engine) as db:
        db.add(Invoice(id='unclassified',organization_id='a',customer_id='ca',invoice_number='BASIC',due_date=today(),total_paise=5000));db.add(InvoiceMemo(organization_id='a',invoice_id=doc['invoice_id'],kind='credit',number='INTERNAL',amount_paise=1000,reason='Internal credit',actor_id='alice'));db.commit()
    path=f"/api/v1/organizations/a/tax/register?start={doc['issue_date']}&end={doc['issue_date']}"
    response=c.get(path);assert response.status_code==200,response.text;r=response.json()
    assert r['document_count']==1 and r['line_count']==1 and r['totals']['taxable_paise']==10000 and r['totals']['total_paise']==11800
    assert r['totals']['cgst_paise']==900 and r['totals']['sgst_paise']==900 and r['totals']['utgst_paise']==0
    assert r['unclassified_invoice_count_all_dates']==1 and r['portal_connected'] is False
    with Session(engine) as db:
        source=db.get(TradeDocument,doc['id']);source.issue_date=today()-timedelta(days=2);db.commit()
    assert c.get(path).json()['document_count']==0
    who['id']='viewer';assert c.get(path).status_code==200
    who['id']='bob';assert c.get(path).status_code==403


def test_registration_filter_and_utgst_are_separate_from_sgst(api):
    c,who,engine=api;c.app.include_router(router);product=setup(c)
    c.post(BASE+'/products/'+product,json={'sku':'SKU-1','name':'Service','unit':'NOS','hsn_sac':'8471','unit_price_paise':10000,'tax_rate_bps':1800,'track_stock':False,'reorder_milliunits':0,'active':True})
    doc=issue(c,product)
    with Session(engine) as db:
        source=db.get(TradeDocument,doc['id']);source.supplier={**source.supplier,'gstin':'38ABCDE1234F1Z5','state_code':'38'};source.totals={**source.totals,'state_tax_label':'UTGST'};db.commit()
    path=f"/api/v1/organizations/a/tax/register?start={doc['issue_date']}&end={doc['issue_date']}"
    result=c.get(path).json();assert result['totals']['utgst_paise']==900 and result['totals']['sgst_paise']==0
    assert c.get(path+'&supplier_gstin=27ABCDE1234F1Z5').json()['document_count']==0
    assert c.get(path+'&supplier_gstin=38ABCDE1234F1Z5').json()['document_count']==1
    assert c.get(f'/api/v1/organizations/a/tax/register?start={today()}&end={today()+timedelta(days=1)}').status_code==422
