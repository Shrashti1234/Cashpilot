from datetime import date,datetime,timedelta,timezone
import hashlib
import secrets
from typing import Annotated

from fastapi import APIRouter,Depends,HTTPException,Request,Response
from pydantic import BaseModel,ConfigDict,Field,model_validator
from sqlalchemy import select,func,and_
from sqlalchemy.orm import Session

from audit import record_event
from auth_identity import get_verified_identity
from buyer_access import BuyerAccess
from disputes import InvoiceDispute
from intelligence_api import today
from operations import BusinessProfile,TradeDocument
from operations_api import authorize,mutation
from promises import PaymentPromise,create_promise,promise_out,received_since
from request_limits import allow_action
from saas_api import get_saas_session
from saas_domain import Customer,Invoice,Payment,Organization,invoice_positions


def no_cache(response:Response):response.headers['Cache-Control']='no-store'


router=APIRouter(prefix='/api/v1',tags=['buyer-access'],dependencies=[Depends(no_cache)])
Identity=Annotated[str,Depends(get_verified_identity)]
Db=Annotated[Session,Depends(get_saas_session)]


class LinkInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    invoice_id:str=Field(min_length=1,max_length=36)
    expires_days:int=Field(default=7,ge=1,le=30,strict=True)
    can_dispute:bool=Field(default=True,strict=True)
    can_promise:bool=Field(default=True,strict=True)


class TokenInput(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    token:str=Field(min_length=40,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')


class PromiseInput(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    amount_paise:int=Field(gt=0,le=2_000_000_000,strict=True)
    promised_date:date
    note:str=Field(default='',max_length=1000)
    request_key:str=Field(min_length=1,max_length=80)

    @model_validator(mode='after')
    def dates(self):
        if not today()<=self.promised_date<=today()+timedelta(days=90):raise ValueError('Promise date must be today through 90 days ahead')
        return self


class BuyerPromise(TokenInput,PromiseInput):pass


class BuyerDispute(TokenInput):
    reason:str=Field(pattern=r'^(amount_mismatch|missing_document|quality|delivery|other)$')
    description:str=Field(min_length=1,max_length=2000)


class CancelPromise(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    reason:str=Field(min_length=1,max_length=1000)


def utc(value):return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def link_out(link):
    return {**{k:getattr(link,k) for k in ['id','invoice_id','revoked','can_dispute','can_promise','view_count']},
            'expires_at':utc(link.expires_at),'last_viewed_at':utc(link.last_viewed_at) if link.last_viewed_at else None}


def public_promise(p,received):
    return {k:v for k,v in promise_out(p,received,today()).items() if k in {'id','amount_paise','promised_date','state','created_at'}}


def capability(db,token,request):
    allow_action(request.client.host if request.client else 'unknown','buyer-attempt','buyer access attempts',limit=120)
    digest=hashlib.sha256(token.encode()).hexdigest()
    link=db.scalar(select(BuyerAccess).where(BuyerAccess.token_hash==digest).with_for_update())
    if not link or link.revoked or utc(link.expires_at)<=datetime.now(timezone.utc):raise HTTPException(404,'Private invoice access is invalid or expired')
    allow_action('buyer-link',link.id,'buyer-link requests')
    return link


@router.get('/organizations/{organization_id}/buyer-access')
def links(organization_id:str,identity:Identity,db:Db):
    authorize(db,identity,organization_id,admin=True)
    records=db.scalars(select(BuyerAccess).where(BuyerAccess.organization_id==organization_id).order_by(BuyerAccess.created_at.desc()).limit(100))
    return {'links':[link_out(link) for link in records]}


@router.post('/organizations/{organization_id}/buyer-access',status_code=201)
def create_link(organization_id:str,payload:LinkInput,identity:Identity,db:Db):
    authorize(db,identity,organization_id,admin=True)
    allow_action(identity,'buyer-link-create','private links')
    with mutation(db):
        inv=db.scalar(select(Invoice).where(Invoice.organization_id==organization_id,Invoice.id==payload.invoice_id))
        if inv is None:raise ValueError('Choose an issued invoice in this business')
        token=secrets.token_urlsafe(32)
        link=BuyerAccess(organization_id=organization_id,invoice_id=inv.id,token_hash=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=datetime.now(timezone.utc)+timedelta(days=payload.expires_days),can_dispute=payload.can_dispute,
            can_promise=payload.can_promise,revoked=False,view_count=0,created_by=identity)
        db.add(link);db.flush();record_event(db,organization_id,identity,'buyer_access.created',link.id)
    return {**link_out(link),'token':token}


@router.post('/organizations/{organization_id}/buyer-access/{link_id}/revoke')
def revoke_link(organization_id:str,link_id:str,identity:Identity,db:Db):
    authorize(db,identity,organization_id,admin=True)
    with mutation(db):
        link=db.scalar(select(BuyerAccess).where(BuyerAccess.organization_id==organization_id,BuyerAccess.id==link_id).with_for_update())
        if link is None:raise HTTPException(404,'Private access not found')
        link.revoked=True;record_event(db,organization_id,identity,'buyer_access.revoked',link.id)
    return link_out(link)


@router.post('/buyer/inspect')
def inspect_invoice(payload:TokenInput,request:Request,db:Db):
    with mutation(db):
        link=capability(db,payload.token,request)
        inv=db.scalar(select(Invoice).where(Invoice.organization_id==link.organization_id,Invoice.id==link.invoice_id).with_for_update(read=True))
        if inv is None:raise HTTPException(404,'Private invoice is unavailable')
        pos=invoice_positions(db,link.organization_id,[inv])[inv.id]
        source=db.scalar(select(TradeDocument).where(TradeDocument.organization_id==link.organization_id,TradeDocument.invoice_id==inv.id,TradeDocument.kind=='invoice'))
        profile=db.get(BusinessProfile,link.organization_id)
        buyer=db.scalar(select(Customer).where(Customer.organization_id==link.organization_id,Customer.id==inv.customer_id))
        org=db.get(Organization,link.organization_id)
        seller={k:source.supplier.get(k,'') for k in ['legal_name','address','gstin']} if source else {'legal_name':profile.legal_name if profile else org.name,'address':profile.address if profile else '','gstin':profile.gstin if profile else ''}
        lines=[{k:line.get(k) for k in ['description','hsn_sac','unit','quantity_milliunits','unit_price_paise','discount_paise','tax_rate_bps','cess_rate_bps','total_paise']} for line in source.lines] if source else []
        dispute=db.scalar(select(InvoiceDispute).where(InvoiceDispute.organization_id==link.organization_id,InvoiceDispute.invoice_id==inv.id))
        promises=list(db.scalars(select(PaymentPromise).where(PaymentPromise.organization_id==link.organization_id,PaymentPromise.invoice_id==inv.id).order_by(PaymentPromise.created_at.desc()).limit(20)))
        link.view_count+=1;link.last_viewed_at=datetime.now(timezone.utc)
        record_event(db,link.organization_id,'buyer-link:'+link.id,'buyer_access.opened',inv.id)
        result={'invoice_number':inv.invoice_number,'due_date':inv.due_date,'original_total_paise':inv.total_paise,
            'adjusted_total_paise':pos['effective_total_paise'],'net_received_paise':pos['paid_paise'],
            'outstanding_paise':pos['outstanding_paise'],'customer_credit_paise':pos['credit_balance_paise'],
            'seller':seller,'recipient_name':source.party.get('name','') if source else buyer.name if buyer else 'Customer',
            'lines':lines,'totals':source.totals if source else None,'currency':'INR','as_of':today(),'expires_at':utc(link.expires_at),
            'permissions':{'can_dispute':link.can_dispute,'can_promise':link.can_promise},
            'dispute':{'status':dispute.status,'reason':dispute.reason} if dispute else None,
            'promises':[public_promise(p,received_since(db,p)) for p in promises],
            'payment_provider_connected':False}
    return result


@router.post('/buyer/promise',status_code=201)
def buyer_promise(payload:BuyerPromise,request:Request,db:Db):
    with mutation(db):
        link=capability(db,payload.token,request)
        if not link.can_promise:raise HTTPException(403,'This private access does not allow payment promises')
        p=create_promise(db,link.organization_id,link.invoice_id,'buyer-link:'+link.id,payload.amount_paise,payload.promised_date,payload.note,'buyer:'+payload.request_key,source='buyer_link')
    return public_promise(p,received_since(db,p))


@router.post('/buyer/dispute',status_code=201)
def buyer_dispute(payload:BuyerDispute,request:Request,db:Db):
    with mutation(db):
        link=capability(db,payload.token,request)
        if not link.can_dispute:raise HTTPException(403,'This private access does not allow disputes')
        db.scalar(select(Invoice).where(Invoice.organization_id==link.organization_id,Invoice.id==link.invoice_id).with_for_update())
        existing=db.scalar(select(InvoiceDispute).where(InvoiceDispute.organization_id==link.organization_id,InvoiceDispute.invoice_id==link.invoice_id))
        if existing:
            if existing.reason==payload.reason and existing.description==payload.description:return {'status':existing.status,'note':'This dispute is already recorded.'}
            raise ValueError('A dispute already exists for this invoice. Contact the business to review additional issues.')
        dispute=InvoiceDispute(organization_id=link.organization_id,invoice_id=link.invoice_id,status='open',reason=payload.reason,description=payload.description)
        db.add(dispute);db.flush();record_event(db,link.organization_id,'buyer-link:'+link.id,'dispute.buyer_opened',dispute.id)
    return {'status':'open'}


@router.get('/organizations/{organization_id}/collections/promises')
def promises(organization_id:str,identity:Identity,db:Db):
    authorize(db,identity,organization_id)
    rows=list(db.scalars(select(PaymentPromise).where(PaymentPromise.organization_id==organization_id).order_by(PaymentPromise.created_at.desc()).limit(1000)))
    totals=dict(db.execute(select(PaymentPromise.id,func.coalesce(func.sum(Payment.amount_paise),0)).outerjoin(Payment,and_(Payment.organization_id==PaymentPromise.organization_id,Payment.invoice_id==PaymentPromise.invoice_id,Payment.created_at>=PaymentPromise.created_at)).where(PaymentPromise.organization_id==organization_id,PaymentPromise.id.in_([p.id for p in rows])).group_by(PaymentPromise.id)).all()) if rows else {}
    return {'promises':[promise_out(p,totals.get(p.id,0),today()) for p in rows]}


@router.post('/organizations/{organization_id}/invoices/{invoice_id}/promise',status_code=201)
def member_promise(organization_id:str,invoice_id:str,payload:PromiseInput,identity:Identity,db:Db):
    authorize(db,identity,organization_id,write=True)
    with mutation(db):p=create_promise(db,organization_id,invoice_id,identity,payload.amount_paise,payload.promised_date,payload.note,'member:'+payload.request_key)
    return promise_out(p,received_since(db,p),today())


@router.post('/organizations/{organization_id}/collections/promises/{promise_id}/cancel')
def cancel_promise(organization_id:str,promise_id:str,payload:CancelPromise,identity:Identity,db:Db):
    authorize(db,identity,organization_id,write=True)
    with mutation(db):
        p=db.scalar(select(PaymentPromise).where(PaymentPromise.organization_id==organization_id,PaymentPromise.id==promise_id))
        if p is None:raise HTTPException(404,'Promise not found')
        db.scalar(select(Invoice).where(Invoice.organization_id==organization_id,Invoice.id==p.invoice_id).with_for_update())
        db.refresh(p)
        if p.status!='pending' or received_since(db,p)>=p.amount_paise:raise ValueError('Only an unfulfilled active promise can be cancelled')
        p.status='cancelled';p.cancellation_note=payload.reason;record_event(db,organization_id,identity,'promise.cancelled',p.id)
    return promise_out(p,received_since(db,p),today())
