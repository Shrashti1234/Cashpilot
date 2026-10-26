"""Recorded facts and receivables analytics; no inferred bank-balance claim."""
from datetime import date,datetime,time,timedelta,timezone
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select,func
from sqlalchemy.orm import Session

from auth_identity import get_verified_identity
from cash_ledger import CashEntry
from cashflow import receivables_aging
from disputes import InvoiceDispute
from intelligence_api import today,payment_day
from operations import Product,StockMovement,TradeDocument
from operations_api import authorize
from saas_api import get_saas_session
from saas_domain import Customer,Invoice,InvoiceRefund,Payment,invoice_positions

router=APIRouter(prefix='/api/v1/organizations/{organization_id}',tags=['business-overview'])
Identity=Annotated[str,Depends(get_verified_identity)]
Db=Annotated[Session,Depends(get_saas_session)]


@router.get('/dashboard')
def dashboard(organization_id:str,identity:Identity,db:Db):
    authorize(db,identity,organization_id)
    now=today();start=now-timedelta(days=29)
    invoices=list(db.scalars(select(Invoice).where(Invoice.organization_id==organization_id).limit(2001)))
    if len(invoices)>2000:raise HTTPException(422,'This overview release supports up to 2,000 invoices per business')
    positions=invoice_positions(db,organization_id,invoices)
    customers={c.id:c.name for c in db.scalars(select(Customer).where(Customer.organization_id==organization_id))}
    months=[]
    for offset in range(5,-1,-1):
        year,month=divmod(now.year*12+now.month-1-offset,12)
        months.append(f'{year:04d}-{month+1:02d}')
    cash=list(db.scalars(select(CashEntry).where(CashEntry.organization_id==organization_id,
        CashEntry.status=='actual',CashEntry.entry_date>=date.fromisoformat(months[0]+'-01'),
        CashEntry.entry_date<=now).limit(10001)))
    if len(cash)>10000:raise HTTPException(422,'Use at most 10,000 cash entries in the six-month overview window')
    activity={str(start+timedelta(days=i)):{'date':str(start+timedelta(days=i)),'inflow_paise':0,'outflow_paise':0} for i in range(30)}
    monthly={m:0 for m in months};expense_dates=set()
    for entry in cash:
        if entry.direction=='out':monthly[str(entry.entry_date)[:7]]+=entry.amount_paise;expense_dates.add(entry.entry_date)
        if entry.entry_date>=start:
            key='inflow_paise' if entry.direction=='in' else 'outflow_paise'
            activity[str(entry.entry_date)][key]+=entry.amount_paise
    utc_start=datetime.combine(start,time.min,tzinfo=ZoneInfo('Asia/Kolkata')).astimezone(timezone.utc)
    for model,key in [(Payment,'inflow_paise'),(InvoiceRefund,'outflow_paise')]:
        records=list(db.scalars(select(model).where(model.organization_id==organization_id,model.created_at>=utc_start).limit(10001)))
        if len(records)>10000:raise HTTPException(422,'Use at most 10,000 receipt/refund records in the 30-day overview window')
        for row in records:
            day=str(payment_day(row.created_at))
            if day in activity:activity[day][key]+=row.amount_paise
    for point in activity.values():point['net_paise']=point['inflow_paise']-point['outflow_paise']
    outstanding=sum(p['outstanding_paise'] for p in positions.values())
    exposures={}
    for inv in invoices:
        exposures[inv.customer_id]=exposures.get(inv.customer_id,0)+positions[inv.id]['outstanding_paise']
    top=sorted([{'id':cid,'name':customers.get(cid,'Customer'),'outstanding_paise':amount,
                 'share':amount/outstanding if outstanding else 0} for cid,amount in exposures.items() if amount>0],
               key=lambda c:(-c['outstanding_paise'],c['id']))[:5]
    aging=receivables_aging([(i.due_date,positions[i.id]['outstanding_paise']) for i in invoices],as_of=now)
    balances=dict(db.execute(select(StockMovement.product_id,func.sum(StockMovement.quantity_milliunits)).where(
        StockMovement.organization_id==organization_id).group_by(StockMovement.product_id)).all())
    products=list(db.scalars(select(Product).where(Product.organization_id==organization_id,Product.active.is_(True),Product.track_stock.is_(True))))
    low=[{'id':p.id,'sku':p.sku,'name':p.name,'stock_milliunits':balances.get(p.id,0),
          'reorder_milliunits':p.reorder_milliunits,'unit':p.unit} for p in products if balances.get(p.id,0)<=p.reorder_milliunits]
    low.sort(key=lambda p:(p['stock_milliunits']-p['reorder_milliunits'],p['id']))
    open_disputes=db.scalar(select(func.count()).select_from(InvoiceDispute).where(InvoiceDispute.organization_id==organization_id,InvoiceDispute.status!='resolved'))
    drafts=db.scalar(select(func.count()).select_from(TradeDocument).where(TradeDocument.organization_id==organization_id,TradeDocument.status.in_(['draft','approved'])))
    overdue=sum(aging[k] for k in ['1_30','31_60','61_90','over_90'])
    alerts=[]
    if overdue:alerts.append({'code':'overdue','title':'Overdue receivables','detail':'Review unpaid balances and any open disputes before following up.','section':'invoices'})
    if top and top[0]['share']>=.5:alerts.append({'code':'concentration','title':'Receivables are concentrated','detail':'One customer accounts for at least half of outstanding invoice balances.','section':'finance'})
    if low:alerts.append({'code':'stock','title':'Stock ledger needs attention','detail':f'{len(low)} product(s) are at or below their reorder threshold.','section':'operations'})
    if len(expense_dates)<28:alerts.append({'code':'history','title':'Limited operating-expense history','detail':'Add complete operating history before relying on learned expense scenarios.','section':'cash'})
    if drafts:alerts.append({'code':'drafts','title':'Documents awaiting review','detail':f'{drafts} draft/approved document(s) have not been issued.','section':'operations'})
    inflow=sum(p['inflow_paise'] for p in activity.values());outflow=sum(p['outflow_paise'] for p in activity.values())
    return {'as_of':now,'currency':'INR','window_start':start,
        'summary':{'customer_count':len(customers),'invoice_count':len(invoices),'outstanding_paise':outstanding,
            'overdue_paise':overdue,'due_next_7_days_paise':sum(positions[i.id]['outstanding_paise'] for i in invoices if now<=i.due_date<=now+timedelta(days=6)),
            'customer_credit_paise':sum(p['credit_balance_paise'] for p in positions.values()),
            'recorded_inflow_paise':inflow,'recorded_outflow_paise':outflow,'net_recorded_cash_paise':inflow-outflow,
            'open_disputes':open_disputes,'drafts_to_review':drafts,'low_stock_count':len(low)},
        'aging':aging,'top_customers':top,'cash_activity':list(activity.values()),
        'operating_expenses_by_month':[{'month':m,'amount_paise':monthly[m]} for m in months],
        'expense_dates_in_window':len(expense_dates),'low_stock':low[:10],'attention':alerts,
        'notes':['Cash activity combines posted invoice receipts, recorded external refunds and actual non-invoice cash entries.',
                 'Net recorded cash is a change in recorded cash, not a reconciled bank balance. Opening cash is not inferred.',
                 'Voided/planned/future cash entries are excluded. Missing expense dates count as zero.',
                 'Customer credits stay attached to their original invoices; disputed outstanding balances remain visible.']}
