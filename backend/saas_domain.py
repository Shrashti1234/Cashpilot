"""Tenant-scoped invoice domain models and operations.

Not mounted as public API routes until verified authentication is integrated.
All service functions require an authenticated user_id resolved by trusted auth.
"""
from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKeyConstraint, Index, Integer, String,
    UniqueConstraint, select, func, true
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class SaaSBase(DeclarativeBase):
    pass


def new_id() -> str:
    return str(uuid4())


class Organization(SaaSBase):
    __tablename__ = "saas_organizations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    mode: Mapped[str] = mapped_column(String(8), nullable=False)
    __table_args__ = (CheckConstraint("mode IN ('micro', 'b2b')"),)


class Membership(SaaSBase):
    __tablename__ = "saas_memberships"
    organization_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    __table_args__ = (
        ForeignKeyConstraint(["organization_id"], ["saas_organizations.id"]),
        CheckConstraint("role IN ('owner', 'admin', 'accountant', 'viewer')"),
    )


class Customer(SaaSBase):
    __tablename__ = "saas_customers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(String(36), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(["organization_id"], ["saas_organizations.id"]),
        UniqueConstraint("organization_id", "id"),
    )


class Invoice(SaaSBase):
    __tablename__ = "saas_invoices"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(String(36), nullable=False)
    customer_id: Mapped[str] = mapped_column(String(36), nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(64), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "customer_id"], ["saas_customers.organization_id", "saas_customers.id"]),
        UniqueConstraint("organization_id", "invoice_number"),
        UniqueConstraint("organization_id", "id"),
        CheckConstraint("total_paise > 0"),
    )


class Payment(SaaSBase):
    __tablename__ = "saas_payments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(String(36), nullable=False)
    invoice_id: Mapped[str] = mapped_column(String(36), nullable=False)
    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "invoice_id"], ["saas_invoices.organization_id", "saas_invoices.id"]),
        UniqueConstraint("organization_id", "idempotency_key"),
        CheckConstraint("amount_paise > 0"),
    )


class InvoiceMemo(SaaSBase):
    """Internal credit/debit adjustment; statutory tax documents are separate."""
    __tablename__ = 'saas_invoice_memos'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(String(36))
    invoice_id: Mapped[str] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(8))
    number: Mapped[str] = mapped_column(String(16))
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    reason: Mapped[str] = mapped_column(String(1000))
    actor_id: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (
        ForeignKeyConstraint(['organization_id', 'invoice_id'], ['saas_invoices.organization_id', 'saas_invoices.id']),
        UniqueConstraint('organization_id', 'kind', 'number'),
        Index('ix_saas_invoice_memos_org_invoice', 'organization_id', 'invoice_id'),
        CheckConstraint("kind IN ('credit', 'debit')"),
        CheckConstraint('amount_paise > 0 AND amount_paise <= 2000000000'),
    )


class InvoiceRefund(SaaSBase):
    """Record of a refund already made outside CashPilot; never initiates one."""
    __tablename__ = 'saas_invoice_refunds'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(String(36))
    invoice_id: Mapped[str] = mapped_column(String(36))
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    reason: Mapped[str] = mapped_column(String(1000))
    idempotency_key: Mapped[str] = mapped_column(String(100))
    actor_id: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (
        ForeignKeyConstraint(['organization_id', 'invoice_id'], ['saas_invoices.organization_id', 'saas_invoices.id']),
        UniqueConstraint('organization_id', 'idempotency_key'),
        Index('ix_saas_invoice_refunds_org_invoice', 'organization_id', 'invoice_id'),
        CheckConstraint('amount_paise > 0 AND amount_paise <= 2000000000'),
    )


def invoice_positions(db: Session, organization_id: str, invoices: list[Invoice]) -> dict:
    """One organization-scoped aggregate per ledger; no per-invoice N+1 reads."""
    amounts = {i.id: {'effective_total_paise': i.total_paise, 'gross_paid_paise': 0,
                      'refunded_paise': 0, 'credit_paise': 0, 'debit_paise': 0} for i in invoices}
    if not amounts:
        return {}
    for model, key in [(Payment, 'gross_paid_paise'), (InvoiceRefund, 'refunded_paise')]:
        for invoice_id, total in db.execute(select(model.invoice_id, func.sum(model.amount_paise)).where(
                model.organization_id == organization_id, model.invoice_id.in_(amounts)).group_by(model.invoice_id)):
            amounts[invoice_id][key] = total
    for invoice_id, kind, total in db.execute(select(InvoiceMemo.invoice_id, InvoiceMemo.kind, func.sum(InvoiceMemo.amount_paise)).where(
            InvoiceMemo.organization_id == organization_id, InvoiceMemo.invoice_id.in_(amounts)).group_by(InvoiceMemo.invoice_id, InvoiceMemo.kind)):
        amounts[invoice_id][kind + '_paise'] = total
    for row in amounts.values():
        row['effective_total_paise'] += row['debit_paise'] - row['credit_paise']
        row['paid_paise'] = row['gross_paid_paise'] - row['refunded_paise']
        balance = row['effective_total_paise'] - row['paid_paise']
        row['outstanding_paise'] = max(balance, 0)
        row['credit_balance_paise'] = max(-balance, 0)
    return amounts


class TenantAccessDenied(PermissionError):
    pass


def require_member(db: Session, user_id: str, organization_id: str, *, write: bool = False) -> Membership:
    membership = db.get(Membership, (organization_id, user_id))
    if membership is None or not membership.active or (write and membership.role == "viewer"):
        raise TenantAccessDenied("Not authorized for this organization")
    return membership


def list_invoices(db: Session, *, user_id: str, organization_id: str) -> list[Invoice]:
    require_member(db, user_id, organization_id)
    return list(db.scalars(select(Invoice).where(Invoice.organization_id == organization_id)))


def create_invoice(
    db: Session, *, user_id: str, organization_id: str, customer_id: str,
    invoice_number: str, due_date: date, total_paise: int
) -> Invoice:
    require_member(db, user_id, organization_id, write=True)
    if total_paise <= 0 or not invoice_number.strip():
        raise ValueError("Invoice number and positive total are required")
    customer = db.scalar(select(Customer).where(Customer.organization_id == organization_id, Customer.id == customer_id))
    if customer is None:
        raise ValueError("Customer not found in this organization")
    invoice = Invoice(organization_id=organization_id, customer_id=customer_id,
                      invoice_number=invoice_number.strip(), due_date=due_date, total_paise=total_paise)
    db.add(invoice)
    db.flush()
    return invoice


def record_payment(
    db: Session, *, user_id: str, organization_id: str, invoice_id: str,
    amount_paise: int, idempotency_key: str
) -> Payment:
    """Serialize payment posting with invoice adjustments using a row lock."""
    require_member(db, user_id, organization_id, write=True)
    if amount_paise <= 0 or not idempotency_key.strip():
        raise ValueError("Positive payment and idempotency key required")
    invoice = db.scalar(select(Invoice).where(
        Invoice.organization_id == organization_id, Invoice.id == invoice_id).with_for_update())
    if invoice is None:
        raise ValueError("Invoice not found in this organization")
    existing = db.scalar(select(Payment).where(
        Payment.organization_id == organization_id, Payment.idempotency_key == idempotency_key))
    if existing:
        if existing.invoice_id != invoice_id or existing.amount_paise != amount_paise:
            raise ValueError("Idempotency key reused with different payment")
        return existing
    position = invoice_positions(db, organization_id, [invoice])[invoice.id]
    if amount_paise > position['outstanding_paise']:
        raise ValueError("Payment exceeds outstanding balance")
    payment = Payment(organization_id=organization_id, invoice_id=invoice_id,
                      amount_paise=amount_paise, idempotency_key=idempotency_key)
    db.add(payment)
    db.flush()
    return payment
