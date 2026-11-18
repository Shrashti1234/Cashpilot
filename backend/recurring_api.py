from datetime import date
from typing import Annotated

from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field,model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from audit import record_event
from auth_identity import get_verified_identity
from intelligence_api import today
from operations import TradeDocument
from operations_api import authorize,mutation
from recurring import RecurringRule,generate_due
from saas_api import get_saas_session
from saas_domain import lock_organization

router=APIRouter(prefix='/api/v1/organizations/{organization_id}/operations/recurring',tags=['recurring-invoice-drafts'])
Identity=Annotated[str,Depends(get_verified_identity)]
Db=Annotated[Session,Depends(get_saas_session)]


class RuleInput(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    source_document_id:str=Field(min_length=1,max_length=36)
    name:str=Field(min_length=1,max_length=100)
    prefix:str=Field(min_length=1,max_length=5,pattern=r'^[A-Za-z0-9-]+$')
    frequency:str=Field(pattern=r'^(weekly|monthly)$')
    interval:int=Field(default=1,ge=1,le=52,strict=True)
    start_date:date
    end_date:date|None=None
    terms_days:int=Field(default=30,ge=0,le=365,strict=True)

    @model_validator(mode='after')
    def dates(self):
        if not date(2000,1,1)<=self.start_date<=date(2090,1,1):raise ValueError('Start date is outside the supported range')
        if self.end_date and not self.start_date<=self.end_date<=date(2099,12,31):raise ValueError('End date must follow the start date')
        if self.frequency=='monthly' and self.interval>12:raise ValueError('Monthly interval must be at most 12')
        return self


class ActiveInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    active:bool=Field(strict=True)


def out(r):
    return {k:getattr(r,k) for k in ['id','name','prefix','frequency','interval','next_date','end_date','terms_days','sequence','active']}


@router.get('')
def list_rules(organization_id:str,identity:Identity,db:Db):
    authorize(db,identity,organization_id)
    return {'rules':[out(r) for r in db.scalars(select(RecurringRule).where(RecurringRule.organization_id==organization_id).order_by(RecurringRule.name))]}


@router.post('',status_code=201)
def create_rule(organization_id:str,payload:RuleInput,identity:Identity,db:Db):
    authorize(db,identity,organization_id,admin=True)
    with mutation(db):
        source=db.scalar(select(TradeDocument).where(TradeDocument.organization_id==organization_id,
            TradeDocument.id==payload.source_document_id,TradeDocument.kind=='invoice',TradeDocument.status!='cancelled'))
        if source is None:raise ValueError('Choose an invoice document in this business')
        snapshot={k:getattr(source,k) for k in ['customer_id','party','supplier','lines','totals','notes']}
        snapshot['source_document_id']=source.id
        r=RecurringRule(organization_id=organization_id,name=payload.name,prefix=payload.prefix,
            frequency=payload.frequency,interval=payload.interval,anchor_day=payload.start_date.day,
            next_date=payload.start_date,end_date=payload.end_date,terms_days=payload.terms_days,
            template=snapshot,created_by=identity,sequence=1,active=True)
        db.add(r);db.flush();record_event(db,organization_id,identity,'recurrence.created',r.id)
    return out(r)


@router.post('/generate')
def run_due(organization_id:str,identity:Identity,db:Db):
    authorize(db,identity,organization_id,write=True)
    with mutation(db):result=generate_due(db,organization_id,identity,today())
    return result


@router.post('/{rule_id}/active')
def toggle_rule(organization_id:str,rule_id:str,payload:ActiveInput,identity:Identity,db:Db):
    authorize(db,identity,organization_id,admin=True)
    with mutation(db):
        # Same organization lock order as generation avoids policy/run races.
        lock_organization(db,organization_id)
        r=db.scalar(select(RecurringRule).where(RecurringRule.organization_id==organization_id,RecurringRule.id==rule_id).with_for_update())
        if r is None:raise HTTPException(404,'Recurring series not found')
        if payload.active and ((r.end_date and r.next_date>r.end_date) or r.sequence>9999):raise ValueError('This series is complete; create a new one')
        r.active=payload.active;record_event(db,organization_id,identity,'recurrence.resumed' if payload.active else 'recurrence.paused',r.id)
    return out(r)
