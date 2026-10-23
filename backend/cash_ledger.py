"""Business-owned actual operating cash history and explicit future plans."""
from datetime import date, datetime, timezone
from uuid import uuid4
from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column
from saas_domain import SaaSBase


class CashEntry(SaaSBase):
    __tablename__ = "saas_cash_entries"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("saas_organizations.id"), nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(8), nullable=False)
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    description: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (
        CheckConstraint("direction IN ('in', 'out')"), CheckConstraint("status IN ('actual', 'planned', 'void')"),
        CheckConstraint("amount_paise > 0 AND amount_paise <= 1000000000000"),
        Index("ix_cash_entries_org_date", "organization_id", "entry_date"),
    )
