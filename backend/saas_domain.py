"""Tenant-scoped invoice domain models and operations.

Not mounted as public API routes until verified authentication is integrated.
All service functions require an authenticated user_id resolved by trusted auth.
"""
from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint, Date, DateTime, ForeignKeyConstraint, Integer, String,
    UniqueConstraint, select
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


class TenantAccessDenied(PermissionError):
    pass


def require_member(db: Session, user_id: str, organization_id: str, *, write: bool = False) -> Membership:
    membership = db.get(Membership, (organization_id, user_id))
    if membership is None or (write and membership.role == "viewer"):
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
    """Caller must run this in a transaction and lock the invoice row on PostgreSQL."""
    require_member(db, user_id, organization_id, write=True)
    if amount_paise <= 0 or not idempotency_key.strip():
        raise ValueError("Positive payment and idempotency key required")
    existing = db.scalar(select(Payment).where(
        Payment.organization_id == organization_id, Payment.idempotency_key == idempotency_key))
    if existing:
        if existing.invoice_id != invoice_id or existing.amount_paise != amount_paise:
            raise ValueError("Idempotency key reused with different payment")
        return existing
    invoice = db.scalar(select(Invoice).where(
        Invoice.organization_id == organization_id, Invoice.id == invoice_id).with_for_update())
    if invoice is None:
        raise ValueError("Invoice not found in this organization")
    paid = sum(db.scalars(select(Payment.amount_paise).where(
        Payment.organization_id == organization_id, Payment.invoice_id == invoice_id)))
    if amount_paise > invoice.total_paise - paid:
        raise ValueError("Payment exceeds outstanding balance")
    payment = Payment(organization_id=organization_id, invoice_id=invoice_id,
                      amount_paise=amount_paise, idempotency_key=idempotency_key)
    db.add(payment)
    db.flush()
    return payment
