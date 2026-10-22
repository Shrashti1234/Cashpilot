"""Invoice API router. Mount ONLY after wiring get_verified_identity to a real IdP.

Authentication dependency is deliberately fail-closed. Do not use X-User-ID or
client-supplied user identifiers for production authentication.
"""
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from auth_identity import get_verified_identity
from saas_domain import (
    Customer, Invoice, TenantAccessDenied, create_invoice, list_invoices,
    record_payment, require_member,
)
from sqlalchemy import select

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
    total_paise: int = Field(gt=0)


class PaymentCreate(BaseModel):
    amount_paise: int = Field(gt=0)
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
        return {"invoices": [invoice_out(x) for x in list_invoices(
            db, user_id=identity, organization_id=organization_id)]}
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
        db.commit()
        db.refresh(customer)
        return {"id": customer.id, "name": customer.name}
    except TenantAccessDenied:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/invoices", status_code=201)
def add_invoice(organization_id: str, payload: InvoiceCreate, identity: Identity, db: Db):
    try:
        invoice = create_invoice(
            db, user_id=identity, organization_id=organization_id,
            customer_id=payload.customer_id, invoice_number=payload.invoice_number,
            due_date=payload.due_date, total_paise=payload.total_paise,
        )
        db.commit()
        db.refresh(invoice)
        return invoice_out(invoice)
    except TenantAccessDenied:
        db.rollback()
        raise HTTPException(status_code=403, detail="Forbidden")
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/invoices/{invoice_id}/payments", status_code=201)
def add_payment(organization_id: str, invoice_id: str, payload: PaymentCreate,
                identity: Identity, db: Db):
    try:
        payment = record_payment(
            db, user_id=identity, organization_id=organization_id,
            invoice_id=invoice_id, amount_paise=payload.amount_paise,
            idempotency_key=payload.idempotency_key,
        )
        db.commit()
        return {"id": payment.id, "invoice_id": payment.invoice_id,
                "amount_paise": payment.amount_paise}
    except TenantAccessDenied:
        db.rollback()
        raise HTTPException(status_code=403, detail="Forbidden")
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
