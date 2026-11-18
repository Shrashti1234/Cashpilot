from datetime import datetime,timezone
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,ConfigDict,Field,model_validator
from sqlalchemy import select,func
from audit import record_event
from finance_api import MemoInput,RefundInput,_post_memo,_post_refund,locked_invoice
from financial_approvals import FinancialPolicy,FinancialApproval,locked_writer
from operations_api import authorize,mutation
from saas_api import Identity,Db
from saas_domain import Membership

router=APIRouter(prefix='/api/v1/organizations/{organization_id}/financial-approvals',tags=['independent-financial-approval'])
class StrictInput(BaseModel):model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class PolicyInput(StrictInput):require_approval:bool=Field(strict=True)
class RefundRecordInput(StrictInput):
    amount_paise:int=Field(gt=0,le=2_000_000_000,strict=True)
    reason:str=Field(min_length=1,max_length=1000)
    confirmed_external_refund:bool=Field(default=False,strict=True)
class RequestInput(StrictInput):
    invoice_id:str=Field(min_length=1,max_length=36)
    operation:str=Field(pattern=r'^(memo|refund_record)$')
    memo:MemoInput|None=None
    refund:RefundRecordInput|None=None
    request_key:str=Field(min_length=1,max_length=80)
    @model_validator(mode='after')
    def correct_payload(self):
        if self.operation=='memo' and (self.memo is None or self.refund is not None) or self.operation=='refund_record' and (self.refund is None or self.memo is not None):raise ValueError('Supply exactly the record details for the selected operation')
        if self.refund and not self.refund.confirmed_external_refund:raise ValueError('Confirm the refund already happened outside CashPilot')
        return self
class DecisionInput(StrictInput):
    decision:str=Field(pattern=r'^(approve|reject|cancel)$')
    note:str=Field(min_length=1,max_length=1000)


def out(row):return {k:getattr(row,k) for k in ['id','invoice_id','operation','payload','status','requested_by','decided_by','decision_note','decided_at','posted_id','created_at']}


@router.get('/policy')
def policy(organization_id:str,identity:Identity,db:Db):
    authorize(db,identity,organization_id)
    p=db.get(FinancialPolicy,organization_id)
    count=db.scalar(select(func.count()).select_from(Membership).where(Membership.organization_id==organization_id,Membership.active.is_(True),Membership.role.in_(['owner','admin'])))
    return {'require_approval':bool(p and p.require_approval),'active_approvers':count,'actor_id':identity}


@router.post('/policy')
def set_policy(organization_id:str,payload:PolicyInput,identity:Identity,db:Db):
    with mutation(db):
        locked_writer(db,organization_id,identity,owner=True)
        count=db.scalar(select(func.count()).select_from(Membership).where(Membership.organization_id==organization_id,Membership.active.is_(True),Membership.role.in_(['owner','admin'])))
        if payload.require_approval and count<2:raise ValueError('Add a second active owner or administrator before requiring independent financial approval')
        p=db.get(FinancialPolicy,organization_id)
        if not p:p=FinancialPolicy(organization_id=organization_id);db.add(p)
        p.require_approval=payload.require_approval;p.updated_by=identity;p.updated_at=datetime.now(timezone.utc)
        record_event(db,organization_id,identity,'financial_policy.enabled' if p.require_approval else 'financial_policy.disabled',organization_id)
    return {'require_approval':p.require_approval}


@router.get('')
def requests(organization_id:str,identity:Identity,db:Db):
    authorize(db,identity,organization_id)
    rows=db.scalars(select(FinancialApproval).where(FinancialApproval.organization_id==organization_id).order_by(FinancialApproval.created_at.desc()).limit(200))
    return {'requests':[out(row) for row in rows]}


@router.post('',status_code=201)
def request_approval(organization_id:str,payload:RequestInput,identity:Identity,db:Db):
    with mutation(db):
        locked_writer(db,organization_id,identity,admin=payload.operation=='refund_record')
        locked_invoice(db,organization_id,payload.invoice_id)
        data=payload.memo.model_dump() if payload.memo else payload.refund.model_dump()
        prior=db.scalar(select(FinancialApproval).where(FinancialApproval.organization_id==organization_id,FinancialApproval.request_key==payload.request_key))
        if prior:
            if (prior.invoice_id,prior.operation,prior.payload)!=(payload.invoice_id,payload.operation,data):raise ValueError('Approval request key was already used for different details')
            return out(prior)
        row=FinancialApproval(organization_id=organization_id,invoice_id=payload.invoice_id,operation=payload.operation,payload=data,status='pending',requested_by=identity,request_key=payload.request_key)
        db.add(row);db.flush();record_event(db,organization_id,identity,'financial_request.created',row.id)
    return out(row)


@router.post('/{request_id}/decision')
def decide(organization_id:str,request_id:str,payload:DecisionInput,identity:Identity,db:Db):
    with mutation(db):
        actor=locked_writer(db,organization_id,identity,admin=payload.decision!='cancel')
        row=db.scalar(select(FinancialApproval).where(FinancialApproval.organization_id==organization_id,FinancialApproval.id==request_id).with_for_update())
        if not row:raise HTTPException(404,'Financial request not found')
        expected={'approve':'approved','reject':'rejected','cancel':'cancelled'}[payload.decision]
        if payload.decision=='cancel' and actor.role not in {'owner','admin'} and row.requested_by!=identity:raise HTTPException(403,'Only the requester or an administrator can cancel this request')
        if row.status!='pending':
            if row.status==expected:return out(row)
            raise ValueError('This request has already been decided')
        if payload.decision=='approve':
            if row.requested_by==identity:raise ValueError('A different active owner or administrator must approve this request')
            requester=db.get(Membership,(organization_id,row.requested_by),populate_existing=True)
            if not requester or not requester.active or requester.role=='viewer' or row.operation=='refund_record' and requester.role not in {'owner','admin'}:raise ValueError('Requester no longer has the required active role. Cancel this request and submit a new one.')
            if row.operation=='memo':posted=_post_memo(db,organization_id,row.invoice_id,MemoInput(**row.payload),identity)
            else:posted=_post_refund(db,organization_id,row.invoice_id,RefundInput(**row.payload,idempotency_key='approval:'+row.id),identity)
            row.posted_id=posted.id
        row.status=expected;row.decided_by=identity;row.decision_note=payload.note;row.decided_at=datetime.now(timezone.utc)
        record_event(db,organization_id,identity,'financial_request.'+expected,row.id)
    return out(row)
