"""Tenant-isolated invoice disputes and resolution workflow.

Domain-only module: integrate with authenticated API, migrations, and audit log
before enabling for real customer data. No public buyer token is issued here.
"""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, String, Text, UniqueConstraint, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from saas_domain import SaaSBase, Invoice, TenantAccessDenied, require_member


class InvoiceDispute(SaaSBase):
    __tablename__ = "saas_invoice_disputes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(String(36), nullable=False)
    invoice_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    reason: Mapped[str] = mapped_column(String(30), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "invoice_id"],
                             ["saas_invoices.organization_id", "saas_invoices.id"]),
        UniqueConstraint("organization_id", "invoice_id"),
        CheckConstraint("status IN ('open', 'under_review', 'resolved')"),
        CheckConstraint("reason IN ('amount_mismatch', 'missing_document', 'quality', 'delivery', 'other')"),
    )


def _get_dispute(db: Session, *, organization_id: str, dispute_id: str) -> InvoiceDispute:
    dispute = db.scalar(select(InvoiceDispute).where(
        InvoiceDispute.organization_id == organization_id, InvoiceDispute.id == dispute_id))
    if dispute is None:
        raise ValueError("Dispute not found in this organization")
    return dispute


def open_dispute(db: Session, *, user_id: str, organization_id: str,
                 invoice_id: str, reason: str, description: str) -> InvoiceDispute:
    require_member(db, user_id, organization_id, write=True)
    if reason not in ("amount_mismatch", "missing_document", "quality", "delivery", "other"):
        raise ValueError("Invalid dispute reason")
    if not description.strip():
        raise ValueError("Dispute description required")
    invoice = db.scalar(select(Invoice).where(
        Invoice.organization_id == organization_id, Invoice.id == invoice_id))
    if invoice is None:
        raise ValueError("Invoice not found in this organization")
    if db.scalar(select(InvoiceDispute).where(
        InvoiceDispute.organization_id == organization_id, InvoiceDispute.invoice_id == invoice_id)):
        raise ValueError("An invoice dispute already exists")
    dispute = InvoiceDispute(organization_id=organization_id, invoice_id=invoice_id,
                             reason=reason, description=description.strip(), status="open")
    db.add(dispute)
    db.flush()
    return dispute


def change_dispute_status(db: Session, *, user_id: str, organization_id: str,
                          dispute_id: str, status: str, resolution_note: str | None = None) -> InvoiceDispute:
    require_member(db, user_id, organization_id, write=True)
    dispute = _get_dispute(db, organization_id=organization_id, dispute_id=dispute_id)
    allowed = {"open": {"under_review"}, "under_review": {"resolved"}, "resolved": set()}
    if status not in allowed[dispute.status]:
        raise ValueError("Invalid dispute status transition")
    if status == "resolved" and not (resolution_note and resolution_note.strip()):
        raise ValueError("Resolution note required")
    dispute.status = status
    if status == "resolved":
        dispute.resolution_note = resolution_note.strip()
        dispute.resolved_at = datetime.now(timezone.utc)
    db.flush()
    return dispute


def list_disputes(db: Session, *, user_id: str, organization_id: str) -> list[InvoiceDispute]:
    require_member(db, user_id, organization_id)
    return list(db.scalars(select(InvoiceDispute).where(
        InvoiceDispute.organization_id == organization_id)))
