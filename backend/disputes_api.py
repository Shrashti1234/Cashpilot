"""Authenticated dispute workflow and tenant-scoped audit history."""
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,Field
from sqlalchemy import select
from audit import AuditEvent,record_event
from disputes import open_dispute,change_dispute_status,list_disputes
from saas_api import Identity,Db
from saas_domain import TenantAccessDenied,require_member

router=APIRouter(prefix='/api/v1/organizations/{organization_id}',tags=['disputes'])


class NewDispute(BaseModel):
    invoice_id:str=Field(min_length=1,max_length=36)
    reason:str
    description:str=Field(min_length=1,max_length=2000)


class StatusChange(BaseModel):
    status:str
    resolution_note:str|None=Field(default=None,max_length=2000)


def out(d):
    return {k:getattr(d,k) for k in ['id','invoice_id','status','reason','description','resolution_note','opened_at','resolved_at']}


@router.get('/disputes')
def get_disputes(organization_id:str,identity:Identity,db:Db):
    try:return {'disputes':[out(d) for d in list_disputes(db,user_id=identity,organization_id=organization_id)]}
    except TenantAccessDenied:raise HTTPException(403,'Forbidden') from None


@router.post('/disputes',status_code=201)
def create_dispute(organization_id:str,payload:NewDispute,identity:Identity,db:Db):
    try:
        dispute=open_dispute(db,user_id=identity,organization_id=organization_id,**payload.model_dump())
        record_event(db,organization_id,identity,'dispute.opened',dispute.id);db.commit();db.refresh(dispute)
        return out(dispute)
    except TenantAccessDenied:db.rollback();raise HTTPException(403,'Forbidden') from None
    except ValueError as exc:db.rollback();raise HTTPException(422,str(exc)) from None


@router.post('/disputes/{dispute_id}/status')
def update_dispute(organization_id:str,dispute_id:str,payload:StatusChange,identity:Identity,db:Db):
    try:
        d=change_dispute_status(db,user_id=identity,organization_id=organization_id,dispute_id=dispute_id,**payload.model_dump())
        record_event(db,organization_id,identity,'dispute.'+payload.status,d.id);db.commit();db.refresh(d)
        return out(d)
    except TenantAccessDenied:db.rollback();raise HTTPException(403,'Forbidden') from None
    except ValueError as exc:db.rollback();raise HTTPException(422,str(exc)) from None


@router.get('/audit')
def audit_history(organization_id:str,identity:Identity,db:Db):
    try:require_member(db,identity,organization_id)
    except TenantAccessDenied:raise HTTPException(403,'Forbidden') from None
    events=db.scalars(select(AuditEvent).where(AuditEvent.organization_id==organization_id).order_by(AuditEvent.occurred_at.desc()).limit(100))
    return {'events':[{'id':e.id,'actor_id':e.actor_id,'action':e.action,'resource_id':e.resource_id,'occurred_at':e.occurred_at.isoformat()} for e in events]}
