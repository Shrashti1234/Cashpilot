from typing import Annotated, Literal
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import and_,or_,select,func
from sqlalchemy.orm import Session
from audit import record_event
from auth_identity import get_verified_identity
from banking import BankAccount,BankTransaction,BankMatch,parse_statement
from cash_ledger import CashEntry
from intelligence_api import today,payment_day
from operations_api import authorize,mutation
from saas_api import get_saas_session
from saas_domain import Customer,Invoice,Payment,InvoiceRefund,lock_organization

router=APIRouter(prefix='/api/v1/organizations/{organization_id}/banking',tags=['statement-reconciliation'])
Identity=Annotated[str,Depends(get_verified_identity)]
Db=Annotated[Session,Depends(get_saas_session)]


class StrictInput(BaseModel):model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class AccountInput(StrictInput):label:str=Field(min_length=1,max_length=100)
class StatementInput(StrictInput):csv_text:str=Field(min_length=1,max_length=1_000_000)
class MatchInput(StrictInput):
    kind:str=Field(pattern=r'^(payment|refund|cash_entry)$')
    target_id:str=Field(min_length=1,max_length=36)
    note:str=Field(min_length=1,max_length=1000)
    confirmed:bool=Field(default=False,strict=True)
class ReversalInput(StrictInput):reason:str=Field(min_length=1,max_length=1000)


def account(db,org,account_id,lock=False):
    if lock:lock_organization(db,org)
    query=select(BankAccount).where(BankAccount.organization_id==org,BankAccount.id==account_id)
    row=db.scalar(query)
    if not row:raise HTTPException(404,'Statement account not found')
    return row


def transaction(db,org,transaction_id):
    # Statement evidence has no UPDATE grant. Serialize reconciliation through
    # the organization's control lock instead of locking immutable evidence.
    lock_organization(db,org)
    row=db.scalar(select(BankTransaction).where(BankTransaction.organization_id==org,BankTransaction.id==transaction_id))
    if not row:raise HTTPException(404,'Statement row not found')
    return row


def match_out(m):return {k:getattr(m,k) for k in ['id','transaction_id','payment_id','refund_id','cash_entry_id','active','note','reversal_reason']}


def classify_rows(db,org,account_id,rows):
    existing={r.reference:r for r in db.scalars(select(BankTransaction).where(BankTransaction.organization_id==org,BankTransaction.account_id==account_id,BankTransaction.reference.in_([r['reference'] for r in rows])))}
    fresh=[]
    for row in rows:
        prior=existing.get(row['reference'])
        if prior:
            if any(getattr(prior,k)!=v for k,v in row.items()):raise ValueError('An existing bank reference has different details. Import cancelled; review the original statement.')
        else:fresh.append(row)
    return fresh,len(rows)-len(fresh)


@router.get('/accounts')
def accounts(organization_id:str,identity:Identity,db:Db):
    authorize(db,identity,organization_id)
    rows=db.scalars(select(BankAccount).where(BankAccount.organization_id==organization_id).order_by(BankAccount.label))
    return {'accounts':[{'id':r.id,'label':r.label,'currency':'INR'} for r in rows]}


@router.post('/accounts',status_code=201)
def add_account(organization_id:str,payload:AccountInput,identity:Identity,db:Db):
    authorize(db,identity,organization_id,admin=True)
    with mutation(db):
        prior=db.scalar(select(BankAccount).where(BankAccount.organization_id==organization_id,BankAccount.label==payload.label))
        if prior:return {'id':prior.id,'label':prior.label,'currency':'INR'}
        row=BankAccount(organization_id=organization_id,label=payload.label);db.add(row);db.flush();record_event(db,organization_id,identity,'bank_account.created',row.id)
    return {'id':row.id,'label':row.label,'currency':'INR'}


@router.post('/accounts/{account_id}/preview')
def preview_statement(organization_id:str,account_id:str,payload:StatementInput,identity:Identity,db:Db):
    authorize(db,identity,organization_id,write=True);account(db,organization_id,account_id)
    try:rows=parse_statement(payload.csv_text,today());fresh,duplicates=classify_rows(db,organization_id,account_id,rows)
    except ValueError as e:raise HTTPException(422,str(e))
    return {'row_count':len(rows),'new_count':len(fresh),'duplicate_count':duplicates,'new_net_change_paise':sum(r['amount_paise'] for r in fresh),'sample':rows[:20]}


@router.post('/accounts/{account_id}/import',status_code=201)
def import_statement(organization_id:str,account_id:str,payload:StatementInput,identity:Identity,db:Db):
    authorize(db,identity,organization_id,write=True)
    with mutation(db):
        account(db,organization_id,account_id,lock=True)
        rows=parse_statement(payload.csv_text,today());fresh,duplicates=classify_rows(db,organization_id,account_id,rows)
        for data in fresh:db.add(BankTransaction(organization_id=organization_id,account_id=account_id,imported_by=identity,**data))
        db.flush()
        if fresh:record_event(db,organization_id,identity,'bank_statement.imported',account_id)
    return {'imported':len(fresh),'duplicates':duplicates}


@router.get('/accounts/{account_id}/transactions')
def statement_rows(organization_id:str,account_id:str,identity:Identity,db:Db,
                   view:Literal['all','matched','unmatched']='all',
                   q:Annotated[str,Query(max_length=100)]='',
                   page:Annotated[int,Query(ge=1,le=1_000_000)]=1,
                   page_size:Annotated[int,Query(ge=1,le=100)]=25):
    authorize(db,identity,organization_id);account(db,organization_id,account_id)
    query=select(BankTransaction,BankMatch).outerjoin(BankMatch,(BankMatch.organization_id==BankTransaction.organization_id)&(BankMatch.transaction_id==BankTransaction.id)&BankMatch.active.is_(True)).where(BankTransaction.organization_id==organization_id,BankTransaction.account_id==account_id)
    summary=db.execute(query.with_only_columns(func.count(BankTransaction.id),func.coalesce(func.sum(BankTransaction.amount_paise),0),func.count(BankMatch.id))).one()
    if view=='matched':query=query.where(BankMatch.id.is_not(None))
    if view=='unmatched':query=query.where(BankMatch.id.is_(None))
    if term:=q.strip():
        query=query.where(or_(BankTransaction.reference.icontains(term,autoescape=True),
                              BankTransaction.description.icontains(term,autoescape=True)))
    total=db.scalar(query.with_only_columns(func.count(BankTransaction.id)))
    rows=db.execute(query.order_by(BankTransaction.booked_date.desc(),BankTransaction.id).offset((page-1)*page_size).limit(page_size))
    return {'summary':{'row_count':summary[0],'imported_net_change_paise':summary[1],'matched_count':summary[2]},'rows':[{**{k:getattr(t,k) for k in ['id','booked_date','reference','description','amount_paise']},'match':match_out(m) if m else None} for t,m in rows],
            'page':page,'page_size':page_size,'total':total,
            'note':'Totals cover all imported rows for this account. Imported net change is not a bank balance. Matching never creates a receipt.'}


TARGETS={'payment':Payment,'refund':InvoiceRefund,'cash_entry':CashEntry}


@router.get('/transactions/{transaction_id}/candidates')
def candidates(organization_id:str,transaction_id:str,identity:Identity,db:Db):
    authorize(db,identity,organization_id,write=True)
    tx=db.scalar(select(BankTransaction).where(BankTransaction.organization_id==organization_id,BankTransaction.id==transaction_id))
    if not tx:raise HTTPException(404,'Statement row not found')
    result=[]
    for kind,model in TARGETS.items():
        if kind=='payment' and tx.amount_paise<0 or kind=='refund' and tx.amount_paise>0:continue
        column=getattr(BankMatch,kind+'_id')
        used=select(column).where(BankMatch.organization_id==organization_id,BankMatch.active.is_(True),column.is_not(None))
        query=select(model).where(model.organization_id==organization_id,model.amount_paise==abs(tx.amount_paise),model.id.not_in(used))
        if kind=='cash_entry':
            query=query.where(CashEntry.status=='actual',CashEntry.direction==('in' if tx.amount_paise>0 else 'out'),CashEntry.entry_date<=today())
            for row in db.scalars(query.order_by(model.created_at.desc(),model.id).limit(200)):
                result.append({'kind':kind,'id':row.id,'amount_paise':row.amount_paise,'date':row.entry_date,'label':row.description})
        else:
            query=(query.add_columns(Invoice.invoice_number,Customer.name)
                   .join(Invoice,and_(Invoice.organization_id==model.organization_id,Invoice.id==model.invoice_id))
                   .join(Customer,and_(Customer.organization_id==Invoice.organization_id,Customer.id==Invoice.customer_id)))
            for row,number,customer in db.execute(query.order_by(model.created_at.desc(),model.id).limit(200)):
                label=f"{'Receipt' if kind=='payment' else 'Refund'} · {number} · {customer}"
                result.append({'kind':kind,'id':row.id,'amount_paise':row.amount_paise,'date':payment_day(row.created_at),'label':label})
    return {'candidates':result,'note':'Exact amounts only. Receipt and refund dates show when they were recorded in CashPilot. Verify the bank reference and booking date before matching. Up to 200 candidates per type.'}


@router.post('/transactions/{transaction_id}/match',status_code=201)
def reconcile(organization_id:str,transaction_id:str,payload:MatchInput,identity:Identity,db:Db):
    authorize(db,identity,organization_id,write=True)
    if not payload.confirmed:raise HTTPException(422,'Confirm this statement row and ledger record represent the same transaction')
    with mutation(db):
        tx=transaction(db,organization_id,transaction_id)
        active=db.scalar(select(BankMatch).where(BankMatch.organization_id==organization_id,BankMatch.transaction_id==tx.id,BankMatch.active.is_(True)))
        if active:
            if getattr(active,payload.kind+'_id')==payload.target_id:return match_out(active)
            raise ValueError('Statement row already matched; reverse the match before replacing it')
        model=TARGETS[payload.kind]
        query=select(model).where(model.organization_id==organization_id,model.id==payload.target_id)
        target=db.scalar(query.with_for_update() if payload.kind=='cash_entry' else query)
        if not target:raise ValueError('Choose a ledger record in this business')
        signed=target.amount_paise*(1 if payload.kind=='payment' or payload.kind=='cash_entry' and target.direction=='in' else -1)
        if signed!=tx.amount_paise:raise ValueError('Full amount and direction must match exactly; split payments and fees need separate review')
        if payload.kind=='cash_entry' and (target.status!='actual' or target.entry_date>today()):raise ValueError('Only actual cash records dated today or earlier can be reconciled')
        column=getattr(BankMatch,payload.kind+'_id')
        if db.scalar(select(BankMatch.id).where(BankMatch.organization_id==organization_id,column==target.id,BankMatch.active.is_(True))):raise ValueError('Ledger record is already matched to another statement row')
        row=BankMatch(organization_id=organization_id,transaction_id=tx.id,**{payload.kind+'_id':target.id},active=True,note=payload.note,actor_id=identity)
        db.add(row);db.flush();record_event(db,organization_id,identity,'bank_match.created',row.id)
    return match_out(row)


@router.post('/transactions/{transaction_id}/reverse')
def reverse_match(organization_id:str,transaction_id:str,payload:ReversalInput,identity:Identity,db:Db):
    authorize(db,identity,organization_id,write=True)
    with mutation(db):
        tx=transaction(db,organization_id,transaction_id)
        row=db.scalar(select(BankMatch).where(BankMatch.organization_id==organization_id,BankMatch.transaction_id==tx.id,BankMatch.active.is_(True)).with_for_update())
        if not row:raise ValueError('No active match to reverse')
        row.active=False;row.reversal_reason=payload.reason;row.reversed_by=identity;record_event(db,organization_id,identity,'bank_match.reversed',row.id)
    return match_out(row)


@router.get('/transactions/{transaction_id}/history')
def match_history(organization_id:str,transaction_id:str,identity:Identity,db:Db):
    authorize(db,identity,organization_id)
    tx=db.scalar(select(BankTransaction).where(BankTransaction.organization_id==organization_id,BankTransaction.id==transaction_id))
    if not tx:raise HTTPException(404,'Statement row not found')
    return {'matches':[match_out(m) for m in db.scalars(select(BankMatch).where(BankMatch.organization_id==organization_id,BankMatch.transaction_id==tx.id).order_by(BankMatch.created_at.desc()).limit(100))]}
