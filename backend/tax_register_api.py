"""Recorded tax worksheet. No GST return filing, IRN or compliance certification."""
from datetime import date
from fastapi import APIRouter,HTTPException,Query
from sqlalchemy import select,func
from operations import TradeDocument
from operations_api import authorize
from saas_api import Identity,Db
from saas_domain import Invoice
from business_clock import india_today

router=APIRouter(prefix='/api/v1/organizations/{organization_id}/tax',tags=['recorded-tax-register'])
KEYS=['subtotal_paise','discount_paise','taxable_paise','cgst_paise','sgst_paise','utgst_paise','igst_paise','cess_paise','total_paise']


def tax_values(source,label):
    return {**{key:source[key] for key in KEYS if key not in {'sgst_paise','utgst_paise'}},'sgst_paise':source['state_tax_paise'] if label=='SGST' else 0,'utgst_paise':source['state_tax_paise'] if label=='UTGST' else 0}


def add_totals(destination,values):
    for key in KEYS:destination[key]+=values[key]


@router.get('/register')
def tax_register(organization_id:str,start:date,end:date,identity:Identity,db:Db,supplier_gstin:str|None=Query(default=None,max_length=15,pattern=r'^[A-Z0-9]{15}$')):
    authorize(db,identity,organization_id)
    if start>end or (end-start).days>365 or end>india_today():raise HTTPException(422,'Choose an inclusive period of at most 366 days ending today or earlier')
    documents=list(db.scalars(select(TradeDocument).where(TradeDocument.organization_id==organization_id,TradeDocument.kind=='invoice',TradeDocument.status=='issued',TradeDocument.issue_date>=start,TradeDocument.issue_date<=end).order_by(TradeDocument.issue_date,TradeDocument.number).limit(2001)))
    if len(documents)>2000:raise HTTPException(422,'Use a narrower period; this worksheet supports up to 2,000 issued source documents')
    registrations=sorted({d.supplier.get('gstin','') for d in documents})
    if supplier_gstin is not None:documents=[d for d in documents if d.supplier.get('gstin','')==supplier_gstin]
    if sum(len(d.lines) for d in documents)>10000:raise HTTPException(422,'Use a narrower period; this worksheet supports up to 10,000 source line items')
    totals={key:0 for key in KEYS};by_registration={};hsn={};rows=[];lines=[];missing_codes=0;missing_supplier=0
    for doc in documents:
        label=doc.totals.get('state_tax_label')
        if label not in {'SGST','UTGST'}:raise HTTPException(422,'A source document has an unclassified state-tax label. Review the document before exporting.')
        gstin=doc.supplier.get('gstin','');values=tax_values(doc.totals,label)
        add_totals(totals,values);bucket=by_registration.setdefault(gstin,{key:0 for key in KEYS});add_totals(bucket,values)
        if not gstin:missing_supplier+=1
        rows.append({'id':doc.id,'invoice_id':doc.invoice_id,'number':doc.number,'issue_date':doc.issue_date,'supplier_gstin':gstin,'recipient_name':doc.party.get('name',''),'recipient_gstin':doc.party.get('gstin',''),'place_of_supply':doc.party.get('place_of_supply',''),'tax_regime':doc.totals['tax_regime'],'state_tax_label':label,**values})
        for index,line in enumerate(doc.lines,start=1):
            amounts=tax_values(line,label);code=line.get('hsn_sac','')
            if not code:missing_codes+=1
            key=(gstin,code,line['unit'],line['tax_rate_bps'],line['cess_rate_bps'],label,doc.totals['tax_regime'])
            group=hsn.setdefault(key,{'supplier_gstin':gstin,'hsn_sac':code,'unit':line['unit'],'tax_rate_bps':line['tax_rate_bps'],'cess_rate_bps':line['cess_rate_bps'],'state_tax_label':label,'tax_regime':doc.totals['tax_regime'],'quantity_milliunits':0,**{key:0 for key in KEYS}})
            group['quantity_milliunits']+=line['quantity_milliunits'];add_totals(group,amounts)
            lines.append({'document_id':doc.id,'number':doc.number,'issue_date':doc.issue_date,'line_number':index,'supplier_gstin':gstin,'recipient_gstin':doc.party.get('gstin',''),'description':line['description'],'hsn_sac':code,'unit':line['unit'],'quantity_milliunits':line['quantity_milliunits'],'unit_price_paise':line['unit_price_paise'],'tax_rate_bps':line['tax_rate_bps'],'cess_rate_bps':line['cess_rate_bps'],**amounts})
    sourced=select(TradeDocument.invoice_id).where(TradeDocument.organization_id==organization_id,TradeDocument.kind=='invoice',TradeDocument.status=='issued',TradeDocument.invoice_id.is_not(None))
    missing_count=db.scalar(select(func.count()).select_from(Invoice).where(Invoice.organization_id==organization_id,Invoice.id.not_in(sourced)))
    warnings=['Worksheet of recorded invoice tax components only. This is not a GST return-upload format, IRN request or independently verified tax calculation.',
        'Internal credit/debit memos, receipts and completed-refund records do not change these source tax components. Statutory adjustments require their own reviewed workflow.',
        'Recipient GSTIN, HSN/SAC, rates and registration status are recorded values and have not been verified against portal masters.']
    if missing_count:warnings.append(f'{missing_count} invoices in this business have no issued source tax document. Their issue dates and taxes cannot be allocated to this period and are excluded.')
    if missing_codes:warnings.append(f'{missing_codes} included source lines have no recorded HSN/SAC.')
    if missing_supplier:warnings.append(f'{missing_supplier} included documents have no recorded supplier GSTIN. Review registration and tax applicability separately.')
    return {'start':start,'end':end,'currency':'INR','document_count':len(rows),'line_count':len(lines),'totals':totals,'registration_totals':[{'supplier_gstin':key,**value} for key,value in sorted(by_registration.items())],
        'available_supplier_gstins':registrations,'documents':rows,'lines':lines,'hsn_summary':list(hsn.values()),'unclassified_invoice_count_all_dates':missing_count,'warnings':warnings,
        'portal_connected':False,'sources':[{'title':'GSTN e-invoicing overview','url':'https://www.gstn.org.in/e-invoicing'},{'title':'IRP API setup and sandbox','url':'https://einvoice6.gst.gov.in/content/api-integration/'},{'title':'IRP validation rules','url':'https://einvoice6.gst.gov.in/content/validation-rules/'}]}
