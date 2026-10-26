"""Invoice API router. Mount ONLY after wiring get_verified_identity to a real IdP.

Authentication dependency is deliberately fail-closed. Do not use X-User-ID or
client-supplied user identifiers for production authentication.
"""
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from auth_identity import get_verified_identity
from saas_domain import (
    Customer, Invoice, Payment, TenantAccessDenied, create_invoice, list_invoices,
    record_payment, require_member, invoice_positions,
)
from sqlalchemy import select
from collections_intelligence import Receivable, collections_plan
from disputes import InvoiceDispute
from audit import record_event
from operations import BusinessProfile

router = APIRouter(prefix="/api/v1/organizations/{organization_id}", tags=["invoices"])


def get_saas_session():
    """Override with the production SQLAlchemy session dependency."""
    raise HTTPException(status_code=503, detail="SaaS database not configured")


Identity = Annotated[str, Depends(get_verified_identity)]
Db = Annotated[Session, Depends(get_saas_session)]


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)


class InvoiceCreate(BaseModel):
    customer_id: str
    invoice_number: str = Field(min_length=1, max_length=64)
    due_date: date
    total_paise: int = Field(gt=0, le=2_000_000_000, strict=True)


class PaymentCreate(BaseModel):
    amount_paise: int = Field(gt=0, le=2_000_000_000, strict=True)
    idempotency_key: str = Field(min_length=1, max_length=100)


def invoice_out(invoice: Invoice) -> dict:
    return {
        "id": invoice.id,
        "organization_id": invoice.organization_id,
        "customer_id": invoice.customer_id,
        "invoice_number": invoice.invoice_number,
        "due_date": invoice.due_date.isoformat(),
        "total_paise": invoice.total_paise,
    }


@router.get("/invoices")
def invoices(organization_id: str, identity: Identity, db: Db):
    try:
        rows = list_invoices(db, user_id=identity, organization_id=organization_id)
        positions = invoice_positions(db, organization_id, rows)
        return {"invoices": [{**invoice_out(x), **positions[x.id]} for x in rows]}
    except TenantAccessDenied:
        raise HTTPException(status_code=403, detail="Forbidden")



@router.get("/customers")
def customers(organization_id: str, identity: Identity, db: Db):
    try:
        require_member(db, identity, organization_id)
        records = db.scalars(select(Customer).where(
            Customer.organization_id == organization_id).order_by(Customer.name, Customer.id))
        return {"customers": [{"id": item.id, "name": item.name} for item in records]}
    except TenantAccessDenied:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/customers", status_code=201)
def add_customer(organization_id: str, payload: CustomerCreate, identity: Identity, db: Db):
    try:
        require_member(db, identity, organization_id, write=True)
        if not payload.name.strip():
            raise HTTPException(status_code=422, detail="Customer name is required")
        customer = Customer(organization_id=organization_id, name=payload.name.strip())
        db.add(customer)
        db.flush()
        record_event(db, organization_id, identity, 'customer.created', customer.id)
        db.commit()
        db.refresh(customer)
        return {"id": customer.id, "name": customer.name}
    except TenantAccessDenied:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/invoices", status_code=201)
def add_invoice(organization_id: str, payload: InvoiceCreate, identity: Identity, db: Db):
    try:
        require_member(db, identity, organization_id, write=True)
        profile = db.scalar(select(BusinessProfile).where(BusinessProfile.organization_id == organization_id).with_for_update())
        if profile and profile.require_approval:
            raise HTTPException(422, 'Independent approval is enabled. Prepare and approve an invoice in Products, stock & documents.')
        invoice = create_invoice(
            db, user_id=identity, organization_id=organization_id,
            customer_id=payload.customer_id, invoice_number=payload.invoice_number,
            due_date=payload.due_date, total_paise=payload.total_paise,
        )
        record_event(db, organization_id, identity, 'invoice.created', invoice.id)
        db.commit()
        db.refresh(invoice)
        return invoice_out(invoice)
    except TenantAccessDenied:
        db.rollback()
        raise HTTPException(status_code=403, detail="Forbidden")
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail='This identifier already exists. Refresh and retry.') from None




@router.get("/collections/plan")
def collection_recommendations(organization_id: str, identity: Identity, db: Db):
    """Explainable, human-reviewed recommendations; never contacts customers."""
    try:
        invoices_for_org = list_invoices(db, user_id=identity, organization_id=organization_id)
        if not invoices_for_org:
            return collections_plan([], as_of=date.today())
        ids = [item.id for item in invoices_for_org]
        customers_by_id = {
            item.id: item.name for item in db.scalars(select(Customer).where(
                Customer.organization_id == organization_id))
        }
        positions = invoice_positions(db, organization_id, invoices_for_org)
        disputed_ids = set(db.scalars(select(InvoiceDispute.invoice_id).where(
            InvoiceDispute.organization_id == organization_id,
            InvoiceDispute.invoice_id.in_(ids),
            InvoiceDispute.status != "resolved")))
        receivables = [
            Receivable(invoice_id=invoice.id,
                       customer_name=customers_by_id.get(invoice.customer_id, "Customer"),
                       due_date=invoice.due_date,
                       outstanding_paise=positions[invoice.id]['outstanding_paise'],
                       disputed=invoice.id in disputed_ids)
            for invoice in invoices_for_org
        ]
        return collections_plan(receivables, as_of=date.today())
    except TenantAccessDenied:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.get("/invoices/summary")
def invoice_summary(organization_id: str, identity: Identity, db: Db):
    """Aggregate only invoices and payments belonging to the authorized tenant."""
    try:
        invoices_for_org = list_invoices(db, user_id=identity, organization_id=organization_id)
        positions = invoice_positions(db, organization_id, invoices_for_org)
        today = date.today()
        total = sum(item.total_paise for item in invoices_for_org)
        paid = sum(p['paid_paise'] for p in positions.values())
        overdue = sum(
            positions[item.id]['outstanding_paise']
            for item in invoices_for_org
            if item.due_date < today
        )
        return {"total_invoiced_paise": total, "paid_paise": paid,
                "outstanding_paise": sum(p['outstanding_paise'] for p in positions.values()), "overdue_paise": overdue,
                "invoice_count": len(invoices_for_org),
                "adjusted_invoiced_paise": sum(p['effective_total_paise'] for p in positions.values()),
                "customer_credit_paise": sum(p['credit_balance_paise'] for p in positions.values()),
                "refunded_paise": sum(p['refunded_paise'] for p in positions.values())}
    except TenantAccessDenied:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.get("/invoices/{invoice_id}/payments")
def invoice_payments(organization_id: str, invoice_id: str, identity: Identity, db: Db):
    try:
        require_member(db, identity, organization_id)
        invoice = db.scalar(select(Invoice).where(
            Invoice.organization_id == organization_id, Invoice.id == invoice_id))
        if invoice is None:
            raise HTTPException(status_code=404, detail="Invoice not found")
        payments = db.scalars(select(Payment).where(
            Payment.organization_id == organization_id,
            Payment.invoice_id == invoice_id).order_by(Payment.created_at))
        return {"payments": [{"id": item.id, "amount_paise": item.amount_paise,
                              "created_at": item.created_at.isoformat()}
                             for item in payments]}
    except TenantAccessDenied:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/invoices/{invoice_id}/payments", status_code=201)
def add_payment(organization_id: str, invoice_id: str, payload: PaymentCreate,
                identity: Identity, db: Db):
    try:
        payment = record_payment(
            db, user_id=identity, organization_id=organization_id,
            invoice_id=invoice_id, amount_paise=payload.amount_paise,
            idempotency_key=payload.idempotency_key,
        )
        record_event(db, organization_id, identity, 'payment.recorded_or_replayed', payment.id)
        db.commit()
        return {"id": payment.id, "invoice_id": payment.invoice_id,
                "amount_paise": payment.amount_paise}
    except TenantAccessDenied:
        db.rollback()
        raise HTTPException(status_code=403, detail="Forbidden")
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail='The payment key is already in use. Refresh the payment history.') from None
