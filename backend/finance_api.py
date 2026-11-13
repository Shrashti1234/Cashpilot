"""Credit/debit memos, externally completed refunds and customer statements.

Memos adjust receivables. They are internal records, not certified GST notes.
No endpoint initiates an external payment or refund.
"""
from typing import Annotated
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from audit import record_event
from auth_identity import get_verified_identity
from operations_api import authorize, mutation
from saas_api import get_saas_session
from saas_domain import Customer, Invoice, InvoiceMemo, InvoiceRefund, Payment, invoice_positions
from financial_approvals import guard_direct_post

router = APIRouter(prefix='/api/v1/organizations/{organization_id}', tags=['financial-ledger'])
Identity = Annotated[str, Depends(get_verified_identity)]
Db = Annotated[Session, Depends(get_saas_session)]


class MemoInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    kind: str = Field(pattern=r'^(credit|debit)$')
    number: str = Field(min_length=1, max_length=16, pattern=r'^[A-Za-z0-9/-]+$')
    amount_paise: int = Field(gt=0, le=2_000_000_000, strict=True)
    reason: str = Field(min_length=1, max_length=1000)


class RefundInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    amount_paise: int = Field(gt=0, le=2_000_000_000, strict=True)
    reason: str = Field(min_length=1, max_length=1000)
    idempotency_key: str = Field(min_length=1, max_length=100)
    confirmed_external_refund: bool = False


def locked_invoice(db, organization_id, invoice_id):
    row = db.scalar(select(Invoice).where(Invoice.organization_id == organization_id,
                                          Invoice.id == invoice_id).with_for_update())
    if row is None:
        raise HTTPException(404, 'Invoice not found')
    return row


def memo_out(m):
    return {**{k: getattr(m, k) for k in ['id', 'invoice_id', 'kind', 'number', 'amount_paise', 'reason']}, 'created_at': timestamp(m.created_at)}


def refund_out(r):
    return {**{k: getattr(r, k) for k in ['id', 'invoice_id', 'amount_paise', 'reason']}, 'created_at': timestamp(r.created_at)}


def timestamp(value):
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()


@router.get('/invoices/{invoice_id}/ledger')
def invoice_ledger(organization_id: str, invoice_id: str, identity: Identity, db: Db):
    authorize(db, identity, organization_id)
    invoice = db.scalar(select(Invoice).where(Invoice.organization_id == organization_id, Invoice.id == invoice_id))
    if invoice is None:
        raise HTTPException(404, 'Invoice not found')
    memos = list(db.scalars(select(InvoiceMemo).where(InvoiceMemo.organization_id == organization_id,
                                               InvoiceMemo.invoice_id == invoice_id).order_by(InvoiceMemo.created_at, InvoiceMemo.id).limit(2001)))
    refunds = list(db.scalars(select(InvoiceRefund).where(InvoiceRefund.organization_id == organization_id,
                                                   InvoiceRefund.invoice_id == invoice_id).order_by(InvoiceRefund.created_at, InvoiceRefund.id).limit(2001)))
    payments = list(db.scalars(select(Payment).where(Payment.organization_id == organization_id,
                                                    Payment.invoice_id == invoice_id).order_by(Payment.created_at, Payment.id).limit(2001)))
    if max(len(memos), len(refunds), len(payments)) > 2000:
        raise HTTPException(422, 'This release supports up to 2,000 entries per invoice ledger category')
    return {'invoice_id': invoice.id, 'invoice_number': invoice.invoice_number, 'original_total_paise': invoice.total_paise, 'opening_receivable': invoice.opening_receivable,
            **invoice_positions(db, organization_id, [invoice])[invoice.id],
            'memos': [memo_out(m) for m in memos], 'refunds': [refund_out(r) for r in refunds],
            'payments': [{'id': p.id, 'amount_paise': p.amount_paise, 'created_at': timestamp(p.created_at)} for p in payments]}


@router.post('/invoices/{invoice_id}/memos', status_code=201)
def add_memo(organization_id: str, invoice_id: str, payload: MemoInput, identity: Identity, db: Db):
    authorize(db, identity, organization_id, write=True)
    with mutation(db):
        guard_direct_post(db,organization_id,identity)
        memo = _post_memo(db,organization_id,invoice_id,payload,identity)
    return memo_out(memo)


def _post_memo(db,organization_id,invoice_id,payload,identity):
    """Trusted posting primitive. Caller owns authorization and transaction."""
    invoice=locked_invoice(db,organization_id,invoice_id)
    prior=db.scalar(select(InvoiceMemo).where(InvoiceMemo.organization_id==organization_id,InvoiceMemo.kind==payload.kind,InvoiceMemo.number==payload.number))
    if prior:
        if (prior.invoice_id,prior.amount_paise,prior.reason)!=(invoice_id,payload.amount_paise,payload.reason):raise ValueError('This memo number was already used for different details')
        return prior
    position=invoice_positions(db,organization_id,[invoice])[invoice.id]
    new_total=position['effective_total_paise']+(payload.amount_paise if payload.kind=='debit' else -payload.amount_paise)
    if not 0<=new_total<=2_000_000_000:raise ValueError('Adjusted invoice total must remain between zero and INR 2 crore')
    memo=InvoiceMemo(organization_id=organization_id,invoice_id=invoice_id,actor_id=identity,**payload.model_dump())
    db.add(memo);db.flush();record_event(db,organization_id,identity,'invoice.'+payload.kind+'_memo',memo.id);return memo


@router.post('/invoices/{invoice_id}/refunds', status_code=201)
def add_refund(organization_id: str, invoice_id: str, payload: RefundInput, identity: Identity, db: Db):
    authorize(db, identity, organization_id, admin=True)
    if not payload.confirmed_external_refund:
        raise HTTPException(422, 'Confirm this refund was already completed outside CashPilot')
    with mutation(db):
        guard_direct_post(db,organization_id,identity,admin=True)
        refund = _post_refund(db,organization_id,invoice_id,payload,identity)
    return refund_out(refund)


def _post_refund(db,organization_id,invoice_id,payload,identity):
    """Record a completed refund; never executes a provider payment."""
    if not payload.confirmed_external_refund:raise ValueError('Confirm this refund was already completed outside CashPilot')
    invoice=locked_invoice(db,organization_id,invoice_id)
    prior=db.scalar(select(InvoiceRefund).where(InvoiceRefund.organization_id==organization_id,InvoiceRefund.idempotency_key==payload.idempotency_key))
    if prior:
        if (prior.invoice_id,prior.amount_paise,prior.reason)!=(invoice_id,payload.amount_paise,payload.reason):raise ValueError('Refund key was already used for different details')
        return prior
    position=invoice_positions(db,organization_id,[invoice])[invoice.id]
    if payload.amount_paise>position['credit_balance_paise']:raise ValueError('Refund exceeds the customer credit. Record a valid credit memo first.')
    refund=InvoiceRefund(organization_id=organization_id,invoice_id=invoice_id,amount_paise=payload.amount_paise,reason=payload.reason,idempotency_key=payload.idempotency_key,actor_id=identity)
    db.add(refund);db.flush();record_event(db,organization_id,identity,'invoice.external_refund_recorded',refund.id);return refund


@router.get('/customers/{customer_id}/statement')
def customer_statement(organization_id: str, customer_id: str, identity: Identity, db: Db):
    authorize(db, identity, organization_id)
    customer = db.scalar(select(Customer).where(Customer.organization_id == organization_id, Customer.id == customer_id))
    if customer is None:
        raise HTTPException(404, 'Customer not found')
    invoices = list(db.scalars(select(Invoice).where(Invoice.organization_id == organization_id,
                                                    Invoice.customer_id == customer_id).order_by(Invoice.due_date, Invoice.id).limit(2001)))
    if len(invoices) > 2000:
        raise HTTPException(422, 'This release supports statements up to 2,000 invoices')
    positions = invoice_positions(db, organization_id, invoices)
    totals = {key: sum(row[key] for row in positions.values()) for key in
              ['effective_total_paise', 'gross_paid_paise', 'refunded_paise', 'paid_paise', 'credit_paise',
               'debit_paise', 'outstanding_paise', 'credit_balance_paise']}
    totals['net_due_paise'] = totals['outstanding_paise'] - totals['credit_balance_paise']
    return {'customer': {'id': customer.id, 'name': customer.name}, 'currency': 'INR', 'totals': totals,
            'invoices': [{'id': i.id, 'invoice_number': i.invoice_number, 'due_date': i.due_date,
                          'original_total_paise': i.total_paise, **positions[i.id]} for i in invoices]}
