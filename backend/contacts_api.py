from datetime import date,datetime,timezone
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,ConfigDict,Field,model_validator
from sqlalchemy import select
from audit import record_event
from contacts import ContactPreference,ContactRecord,ContactConsentChange,last_contacts
from disputes import InvoiceDispute
from intelligence_api import today
from operations_api import authorize,mutation
from promises import unfulfilled_promises
from saas_api import Identity,Db
from saas_domain import Customer,Invoice,Organization,invoice_positions,lock_organization

router=APIRouter(prefix='/api/v1/organizations/{organization_id}/contacts',tags=['contact-preferences'])


class StrictInput(BaseModel):model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class PreferenceInput(StrictInput):
    channel:str=Field(pattern=r'^(email|whatsapp|phone)$')
    status:str=Field(pattern=r'^(granted|revoked|unknown)$')
    evidence:str=Field(min_length=1,max_length=1000)
    expires_on:date|None=None
    @model_validator(mode='after')
    def expiry(self):
        if self.status=='granted' and self.expires_on and self.expires_on<today():raise ValueError('Granted consent expiry must be today or later')
        return self
class RecordInput(StrictInput):
    invoice_id:str=Field(min_length=1,max_length=36)
    channel:str=Field(pattern=r'^(email|whatsapp|phone)$')
    contact_date:date
    note:str=Field(min_length=1,max_length=1000)
    request_key:str=Field(min_length=1,max_length=80)
    confirmed_external_contact:bool=Field(default=False,strict=True)
    @model_validator(mode='after')
    def dates(self):
        if not date(2000,1,1)<=self.contact_date<=today():raise ValueError('Contact date must be from 2000 through today')
        return self
class PreviewInput(StrictInput):
    invoice_id:str=Field(min_length=1,max_length=36)
    channel:str=Field(pattern=r'^(email|whatsapp|phone)$')


def preference_out(p):return {k:getattr(p,k) for k in ['id','customer_id','channel','status','evidence','expires_on','updated_at']}
def contact_out(r):return {k:getattr(r,k) for k in ['id','customer_id','invoice_id','channel','contact_date','note','created_at']}


def customer(db,org,customer_id):
    row=db.scalar(select(Customer).where(Customer.organization_id==org,Customer.id==customer_id))
    if not row:raise HTTPException(404,'Customer not found')
    return row


@router.get('/customers/{customer_id}')
def contact_details(organization_id:str,customer_id:str,identity:Identity,db:Db):
    authorize(db,identity,organization_id);customer(db,organization_id,customer_id)
    prefs=db.scalars(select(ContactPreference).where(ContactPreference.organization_id==organization_id,ContactPreference.customer_id==customer_id))
    records=db.scalars(select(ContactRecord).where(ContactRecord.organization_id==organization_id,ContactRecord.customer_id==customer_id).order_by(ContactRecord.contact_date.desc(),ContactRecord.created_at.desc()).limit(100))
    changes=db.scalars(select(ContactConsentChange).where(ContactConsentChange.organization_id==organization_id,ContactConsentChange.customer_id==customer_id).order_by(ContactConsentChange.created_at.desc()).limit(100))
    return {'preferences':[preference_out(p) for p in prefs],'history':[contact_out(r) for r in records],'consent_changes':[{k:getattr(c,k) for k in ['id','channel','status','evidence','expires_on','created_at']} for c in changes],'last_contact_date':last_contacts(db,organization_id).get(customer_id),'cooldown_days':3,'provider_connected':False}


@router.post('/customers/{customer_id}/preference')
def save_preference(organization_id:str,customer_id:str,payload:PreferenceInput,identity:Identity,db:Db):
    authorize(db,identity,organization_id,admin=True)
    with mutation(db):
        lock_organization(db,organization_id);customer(db,organization_id,customer_id)
        p=db.scalar(select(ContactPreference).where(ContactPreference.organization_id==organization_id,ContactPreference.customer_id==customer_id,ContactPreference.channel==payload.channel))
        if not p:p=ContactPreference(organization_id=organization_id,customer_id=customer_id);db.add(p)
        for k,v in payload.model_dump().items():setattr(p,k,v)
        db.add(ContactConsentChange(organization_id=organization_id,customer_id=customer_id,actor_id=identity,**payload.model_dump()))
        p.updated_by=identity;p.updated_at=datetime.now(timezone.utc);db.flush();record_event(db,organization_id,identity,'contact_preference.'+payload.status,p.id)
    return preference_out(p)


@router.post('/records',status_code=201)
def record_contact(organization_id:str,payload:RecordInput,identity:Identity,db:Db):
    authorize(db,identity,organization_id,write=True)
    if not payload.confirmed_external_contact:raise HTTPException(422,'Confirm the contact already happened outside CashPilot')
    with mutation(db):
        lock_organization(db,organization_id)
        inv=db.scalar(select(Invoice).where(Invoice.organization_id==organization_id,Invoice.id==payload.invoice_id))
        if not inv:raise ValueError('Choose an invoice in this business')
        prior=db.scalar(select(ContactRecord).where(ContactRecord.organization_id==organization_id,ContactRecord.request_key==payload.request_key))
        if prior:
            if any(getattr(prior,k)!=getattr(payload,k) for k in ['invoice_id','channel','contact_date','note']):raise ValueError('Contact key was already used for different details')
            return contact_out(prior)
        r=ContactRecord(organization_id=organization_id,customer_id=inv.customer_id,actor_id=identity,**payload.model_dump(exclude={'confirmed_external_contact'}));db.add(r);db.flush();record_event(db,organization_id,identity,'contact.external_recorded',r.id)
    return contact_out(r)


@router.post('/preview')
def reminder_preview(organization_id:str,payload:PreviewInput,identity:Identity,db:Db):
    authorize(db,identity,organization_id,write=True)
    inv=db.scalar(select(Invoice).where(Invoice.organization_id==organization_id,Invoice.id==payload.invoice_id))
    if not inv:raise HTTPException(404,'Invoice not found')
    current=today();position=invoice_positions(db,organization_id,[inv])[inv.id];reasons=[]
    pref=db.scalar(select(ContactPreference).where(ContactPreference.organization_id==organization_id,ContactPreference.customer_id==inv.customer_id,ContactPreference.channel==payload.channel))
    if not pref or pref.status!='granted':reasons.append('No recorded active consent for this channel. Unknown and revoked preferences block reminder drafts.')
    elif pref.expires_on and pref.expires_on<current:reasons.append('Recorded consent has expired.')
    if position['outstanding_paise']==0:reasons.append('Invoice has no outstanding balance.')
    if inv.due_date>current:reasons.append('Invoice is not due yet.')
    if db.scalar(select(InvoiceDispute.id).where(InvoiceDispute.organization_id==organization_id,InvoiceDispute.invoice_id==inv.id,InvoiceDispute.status!='resolved')):reasons.append('Resolve the open invoice issue before requesting payment.')
    promise=unfulfilled_promises(db,organization_id).get(inv.id)
    if promise and promise['date']>=current:reasons.append('An active payment commitment is due today or later. Review it before another request.')
    last=last_contacts(db,organization_id).get(inv.customer_id)
    if last and (current-last).days<3:reasons.append('Customer was contacted within the three-day cooldown, across all invoices and channels.')
    message=None
    if not reasons:
        buyer=customer(db,organization_id,inv.customer_id);org=db.get(Organization,organization_id);amount=position['outstanding_paise']
        message=f'Hello {buyer.name}, this is {org.name}. Invoice {inv.invoice_number}, due {inv.due_date}, has INR {amount//100:,}.{amount%100:02d} outstanding in our records as of {current}. If you have already paid or need a document corrected, please reply so we can review. Thank you.'
    return {'eligible':not reasons,'reasons':reasons,'draft':message,'as_of':current,'last_contact_date':last,'outstanding_paise':position['outstanding_paise'],'provider_connected':False,'note':'Draft only. No message is sent and no contact is recorded. Review current consent and invoice details before contacting the customer.'}
