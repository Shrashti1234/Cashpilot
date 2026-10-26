"""Private invoice record bundles with checksums; no authenticity certification."""
from datetime import date,datetime,timezone
import hashlib
from io import BytesIO
import json
from zipfile import ZipFile,ZIP_DEFLATED
from sqlalchemy import select,or_
from audit import AuditEvent
from banking import BankAccount,BankTransaction,BankMatch
from contacts import ContactPreference,ContactConsentChange,ContactRecord
from disputes import InvoiceDispute
from finance_api import invoice_ledger
from financial_approvals import FinancialApproval
from operations import TradeDocument,BusinessProfile
from operations_api import authorize
from promises import PaymentPromise,promise_out,received_since
from saas_domain import Invoice,Customer,Organization,lock_organization,new_id
from business_clock import india_today

MAX_ROWS=2000
MAX_BYTES=16_000_000


def fields(row,names):return {k:getattr(row,k) for k in names.split()}
def rows(db,query):
    result=list(db.scalars(query.limit(MAX_ROWS+1)))
    if len(result)>MAX_ROWS:raise ValueError('Invoice record category exceeds the 2,000-entry export limit; no partial bundle was generated')
    return result


def invoice_packet(db,org,invoice_id,actor):
    authorize(db,actor,org,admin=True);lock_organization(db,org)
    invoice=db.scalar(select(Invoice).where(Invoice.organization_id==org,Invoice.id==invoice_id).with_for_update())
    if not invoice:raise ValueError('Invoice not found in this business')
    ledger=invoice_ledger(org,invoice_id,actor,db)
    buyer=db.scalar(select(Customer).where(Customer.organization_id==org,Customer.id==invoice.customer_id))
    business=db.get(Organization,org);profile=db.get(BusinessProfile,org)
    documents=rows(db,select(TradeDocument).where(TradeDocument.organization_id==org,TradeDocument.invoice_id==invoice.id).order_by(TradeDocument.created_at))
    contacts=rows(db,select(ContactRecord).where(ContactRecord.organization_id==org,ContactRecord.invoice_id==invoice.id).order_by(ContactRecord.contact_date,ContactRecord.id))
    changes=rows(db,select(ContactConsentChange).where(ContactConsentChange.organization_id==org,ContactConsentChange.customer_id==invoice.customer_id).order_by(ContactConsentChange.created_at))
    preferences=rows(db,select(ContactPreference).where(ContactPreference.organization_id==org,ContactPreference.customer_id==invoice.customer_id).order_by(ContactPreference.channel))
    promises=rows(db,select(PaymentPromise).where(PaymentPromise.organization_id==org,PaymentPromise.invoice_id==invoice.id).order_by(PaymentPromise.created_at))
    issues=rows(db,select(InvoiceDispute).where(InvoiceDispute.organization_id==org,InvoiceDispute.invoice_id==invoice.id))
    approvals=rows(db,select(FinancialApproval).where(FinancialApproval.organization_id==org,FinancialApproval.invoice_id==invoice.id).order_by(FinancialApproval.created_at))
    receipts=[r['id'] for r in ledger['payments']];refunds=[r['id'] for r in ledger['refunds']]
    matches=rows(db,select(BankMatch).where(BankMatch.organization_id==org,or_(BankMatch.payment_id.in_(receipts),BankMatch.refund_id.in_(refunds))).order_by(BankMatch.created_at))
    bank_rows=rows(db,select(BankTransaction).where(BankTransaction.organization_id==org,BankTransaction.id.in_([m.transaction_id for m in matches])).order_by(BankTransaction.booked_date,BankTransaction.id))
    accounts=rows(db,select(BankAccount).where(BankAccount.organization_id==org,BankAccount.id.in_([t.account_id for t in bank_rows])))
    identifiers={invoice.id,*receipts,*refunds,*[m['id'] for m in ledger['memos']]}
    for group in [documents,contacts,changes,preferences,promises,issues,matches,bank_rows,approvals]:identifiers.update(r.id for r in group)
    events=rows(db,select(AuditEvent).where(AuditEvent.organization_id==org,AuditEvent.resource_id.in_(identifiers)).order_by(AuditEvent.occurred_at,AuditEvent.id))
    return {
        'invoice.json':{'business_id':org,'business_name':business.name,'customer':fields(buyer,'id name'),'invoice':fields(invoice,'id invoice_number customer_id due_date total_paise'),
            'current_business_profile':fields(profile,'legal_name address gstin state_code') if profile else None,
            'note':'Current profile and customer records may differ from the immutable issued document. Missing source documents and issue dates are not reconstructed.'},
        'documents.json':[fields(d,'id kind number status issue_date due_date party supplier lines totals notes created_by approved_by created_at') for d in documents],
        'ledger.json':ledger,
        'approvals.json':[fields(r,'id operation payload status requested_by decided_by decision_note decided_at posted_id created_at') for r in approvals],
        'issues.json':[fields(d,'id status reason description resolution_note opened_at resolved_at') for d in issues],
        'commitments.json':[promise_out(p,received_since(db,p),india_today()) for p in promises],
        'contacts.json':{'completed_external_contacts':[fields(r,'id channel contact_date note actor_id created_at') for r in contacts],
            'current_customer_preferences':[fields(p,'id channel status evidence expires_on updated_by updated_at') for p in preferences],
            'customer_consent_history':[fields(c,'id channel status evidence expires_on actor_id created_at') for c in changes],
            'note':'Business-recorded contacts and consent statements do not independently establish delivery or recipient identity.'},
        'reconciliation.json':{'matches':[fields(m,'id transaction_id payment_id refund_id active note actor_id reversal_reason reversed_by created_at') for m in matches],
            'statement_rows':[fields(t,'id account_id booked_date reference description amount_paise created_at') for t in bank_rows],
            'account_aliases':[fields(a,'id label') for a in accounts],
            'note':'Statement rows are manually imported evidence and are not independently authenticated bank records.'},
        'activity.json':[fields(e,'id actor_id action resource_id occurred_at') for e in events],
    }


def json_value(value):
    if isinstance(value,datetime):return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()
    if isinstance(value,date):return value.isoformat()
    raise TypeError('Unsupported record value')


def make_bundle(packet,org,invoice_id):
    contents={name:json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True,default=json_value).encode('utf-8') for name,value in packet.items()}
    contents['README.txt']=(
        'CashPilot private invoice record bundle\n\n'
        'This contains internal financial records and contact notes. Share only with an intended authorized recipient.\n'
        'Amounts are integer paise unless explicitly labelled otherwise. Timestamps without source timezone are treated as UTC.\n'
        'Records reflect current application data at export; later corrections may change subsequent exports.\n'
        'Internal credit/debit memos are not certified GST notes. Payment and refund records do not independently verify bank settlement.\n'
        'No uploaded delivery documents, original email/WhatsApp messages or provider confirmations are attached by this export.\n'
        'The manifest records SHA-256 file checksums for integrity checking. It is not a digital signature, trusted timestamp or authenticity certificate.\n'
        'Private buyer-link codes, their stored hashes, authentication credentials and replay keys are intentionally excluded.\n'
    ).encode('utf-8')
    if sum(len(value) for value in contents.values())>MAX_BYTES:raise ValueError('Bundle exceeds the 16 MB uncompressed export limit; no partial bundle was generated')
    manifest={'format_version':1,'export_id':new_id(),'generated_at':datetime.now(timezone.utc).isoformat(),'organization_id':org,'invoice_id':invoice_id,
        'files':{name:{'sha256':hashlib.sha256(value).hexdigest(),'bytes':len(value)} for name,value in contents.items()}}
    contents['manifest.json']=json.dumps(manifest,indent=2,sort_keys=True).encode('utf-8')
    output=BytesIO()
    with ZipFile(output,'w',compression=ZIP_DEFLATED) as archive:
        for name,value in contents.items():archive.writestr(name,value)
    return output.getvalue()
