"""Tenant-authorized cash history, model transparency and Decision Lab routes."""
import csv
import io
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from auth_identity import get_verified_identity
from cash_ledger import CashEntry
from audit import record_event
from disputes import InvoiceDispute
from intelligence import demo_inputs, model_bundle, model_report, simulate
from saas_api import get_saas_session
from saas_domain import Customer, Invoice, Payment, TenantAccessDenied, require_member
from request_limits import allow_simulation

router=APIRouter(prefix='/api/v1/organizations/{organization_id}',tags=['intelligence'])
Identity=Annotated[str,Depends(get_verified_identity)]
Db=Annotated[Session,Depends(get_saas_session)]


def today(): return datetime.now(ZoneInfo('Asia/Kolkata')).date()


class CashEntryInput(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=False)
    entry_date: date
    direction: str
    status: str
    amount_paise: int=Field(gt=0,le=1_000_000_000_000,strict=True)
    description: str=Field(min_length=1,max_length=160)

    @model_validator(mode='after')
    def check_values(self):
        if self.direction not in ('in','out') or self.status not in ('actual','planned','void'):
            raise ValueError('Choose in/out and actual/planned/void')
        if not self.description.strip(): raise ValueError('Description is required')
        if not date(2000,1,1)<=self.entry_date<=today()+timedelta(days=365): raise ValueError('Date is outside the supported range')
        if self.status=='actual' and self.entry_date>today(): raise ValueError('Actual cash entries cannot be future-dated')
        return self


class CsvInput(BaseModel):
    csv_text: str=Field(min_length=1,max_length=300_000)


class ReceiptOverride(BaseModel):
    invoice_id: str=Field(min_length=1,max_length=36)
    receipt_date: date


class ExpenseOverride(BaseModel):
    entry_id: str=Field(min_length=1,max_length=36)
    expense_date: date


class SimulationInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    opening_balance_paise: int=Field(ge=-1_000_000_000_000,le=1_000_000_000_000,strict=True)
    horizon_days: int=Field(default=30,ge=1,le=90,strict=True)
    use_demo: bool=False
    receipt_overrides: list[ReceiptOverride]=Field(default_factory=list,max_length=10)
    expense_overrides: list[ExpenseOverride]=Field(default_factory=list,max_length=10)

    @model_validator(mode='after')
    def validate_dates(self):
        for d in [o.receipt_date for o in self.receipt_overrides]+[o.expense_date for o in self.expense_overrides]:
            if not today()<=d<=today()+timedelta(days=365): raise ValueError('Scenario dates must be today through one year ahead')
        if len({o.invoice_id for o in self.receipt_overrides})!=len(self.receipt_overrides) or len({o.entry_id for o in self.expense_overrides})!=len(self.expense_overrides):
            raise ValueError('Duplicate scenario references')
        return self


def authorize(db,identity,organization_id,write=False):
    try: require_member(db,identity,organization_id,write=write)
    except TenantAccessDenied: raise HTTPException(403,'Forbidden') from None


def entry_out(e):
    return {'id':e.id,'entry_date':str(e.entry_date),'direction':e.direction,'status':e.status,'amount_paise':e.amount_paise,'description':e.description}


def tenant_inputs(db,organization_id,as_of):
    invoices=list(db.scalars(select(Invoice).where(Invoice.organization_id==organization_id)))
    if len(invoices)>2000: raise HTTPException(422,'This evaluation release supports at most 2,000 invoices per workspace')
    customers={c.id:c.name for c in db.scalars(select(Customer).where(Customer.organization_id==organization_id))}
    payments=list(db.scalars(select(Payment).where(Payment.organization_id==organization_id).order_by(Payment.created_at,Payment.id)))
    by_invoice={}
    for p in payments:
        paid_day=p.created_at.date()
        if paid_day<=as_of: by_invoice.setdefault(p.invoice_id,[]).append(p)
    history={}; outstanding=[]
    for inv in invoices:
        total=0; settled=None
        for p in by_invoice.get(inv.id,[]):
            total+=p.amount_paise
            if total>=inv.total_paise and settled is None: settled=p.created_at.date()
        if settled:
            history.setdefault(inv.customer_id,[]).append({'due_date':inv.due_date,'paid_date':settled})
        if total<inv.total_paise: outstanding.append((inv,total))
    if len(outstanding)>200: raise HTTPException(422,'This release supports up to 200 outstanding invoices in a simulation')
    disputed=set(db.scalars(select(InvoiceDispute.invoice_id).where(InvoiceDispute.organization_id==organization_id,InvoiceDispute.status!='resolved')))
    invoice_rows=[{'id':i.id,'customer_name':customers.get(i.customer_id,'Customer'),'total_paise':i.total_paise,
                   'outstanding_paise':i.total_paise-paid,'due_date':i.due_date,'history':history.get(i.customer_id,[]),'disputed':i.id in disputed}
                  for i,paid in outstanding]
    entries=list(db.scalars(select(CashEntry).where(CashEntry.organization_id==organization_id).order_by(CashEntry.entry_date)))
    if len(entries)>10000: raise HTTPException(422,'Use at most 10,000 cash entries in this evaluation release')
    entry_rows=[{**entry_out(e),'entry_date':e.entry_date} for e in entries]
    return entry_rows,invoice_rows


@router.get('/cash-entries')
def cash_entries(organization_id:str,identity:Identity,db:Db):
    authorize(db,identity,organization_id)
    records=db.scalars(select(CashEntry).where(CashEntry.organization_id==organization_id).order_by(CashEntry.entry_date.desc()).limit(1000))
    return {'entries':[entry_out(e) for e in records]}


@router.post('/cash-entries',status_code=201)
def add_cash_entry(organization_id:str,payload:CashEntryInput,identity:Identity,db:Db):
    authorize(db,identity,organization_id,True)
    entry=CashEntry(organization_id=organization_id,**payload.model_dump())
    db.add(entry); db.flush()
    record_event(db,organization_id,identity,'cash_entry.created',entry.id)
    db.commit(); db.refresh(entry)
    return entry_out(entry)


@router.post('/cash-entries/import',status_code=201)
def import_cash_entries(organization_id:str,payload:CsvInput,identity:Identity,db:Db):
    authorize(db,identity,organization_id,True)
    try:
        reader=csv.DictReader(io.StringIO(payload.csv_text.lstrip('\ufeff')))
        expected={'date','direction','status','amount_inr','description'}
        if not reader.fieldnames or set(reader.fieldnames)!=expected: raise ValueError('CSV header must be date,direction,status,amount_inr,description')
        entries=[]
        for number,row in enumerate(reader,start=2):
            if number>1001: raise ValueError('Maximum 1,000 rows per import')
            if None in row or any(v is None for v in row.values()): raise ValueError(f'Invalid CSV row {number}')
            amount=Decimal(row['amount_inr'])*100
            if not amount.is_finite() or amount!=amount.to_integral_value(): raise ValueError(f'Invalid paise precision at row {number}')
            validated=CashEntryInput(entry_date=row['date'],direction=row['direction'],status=row['status'],amount_paise=int(amount),description=row['description'])
            entries.append(CashEntry(organization_id=organization_id,**validated.model_dump()))
        if not entries: raise ValueError('CSV has no entries')
        db.add_all(entries)
        record_event(db,organization_id,identity,'cash_entries.imported',f'batch:{len(entries)}')
        db.commit()
        return {'imported':len(entries),'note':'Every submitted row is appended. Review duplicates before importing again.'}
    except (ValueError,InvalidOperation) as exc:
        db.rollback()
        raise HTTPException(422,str(exc)) from None


@router.post('/cash-entries/{entry_id}')
def update_cash_entry(organization_id:str,entry_id:str,payload:CashEntryInput,identity:Identity,db:Db):
    authorize(db,identity,organization_id,True)
    entry=db.scalar(select(CashEntry).where(CashEntry.organization_id==organization_id,CashEntry.id==entry_id))
    if entry is None:raise HTTPException(404,'Cash entry not found in this workspace')
    for key,value in payload.model_dump().items():setattr(entry,key,value)
    record_event(db,organization_id,identity,'cash_entry.updated',entry.id)
    db.commit();db.refresh(entry)
    return entry_out(entry)


@router.get('/intelligence/model')
def intelligence_model(organization_id:str,identity:Identity,db:Db):
    authorize(db,identity,organization_id)
    return {'version':model_bundle()['version'],'evaluation':model_report()}


@router.post('/decision-lab/simulate')
def decision_lab(organization_id:str,payload:SimulationInput,identity:Identity,db:Db):
    authorize(db,identity,organization_id)
    allow_simulation(identity,organization_id)
    as_of=today()
    entries,invoices=demo_inputs(as_of) if payload.use_demo else tenant_inputs(db,organization_id,as_of)
    try:
        result=simulate(payload.opening_balance_paise,entries,invoices,as_of,payload.horizon_days,
                        {o.invoice_id:o.receipt_date for o in payload.receipt_overrides},
                        {o.entry_id:o.expense_date for o in payload.expense_overrides})
    except ValueError as exc: raise HTTPException(422,str(exc)) from None
    result['data_source']='synthetic_demo' if payload.use_demo else 'workspace_records'
    result['planned_expenses']=[{**e,'entry_date':str(e['entry_date'])} for e in entries if e['status']=='planned' and e['direction']=='out' and e['entry_date']>=as_of]
    return result
