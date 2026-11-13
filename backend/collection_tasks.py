from datetime import date
from sqlalchemy import Date, ForeignKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column
from saas_domain import SaaSBase


class CollectionTask(SaaSBase):
    __tablename__ = 'saas_collection_tasks'
    organization_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    invoice_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    assignee: Mapped[str] = mapped_column(String(200))
    follow_up: Mapped[date] = mapped_column(Date)
    note: Mapped[str] = mapped_column(String(500))
    __table_args__ = (
        ForeignKeyConstraint(['organization_id', 'invoice_id'], ['saas_invoices.organization_id', 'saas_invoices.id']),
        ForeignKeyConstraint(['organization_id', 'assignee'], ['saas_memberships.organization_id', 'saas_memberships.user_id']),
    )
