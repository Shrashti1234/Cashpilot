"""Hash-only invoice capabilities, separate from business membership tokens."""
from datetime import datetime,timezone

from sqlalchemy import Boolean,DateTime,ForeignKeyConstraint,Index,Integer,String,UniqueConstraint,false
from sqlalchemy.orm import Mapped,mapped_column

from saas_domain import SaaSBase,new_id


class BuyerAccess(SaaSBase):
    __tablename__='saas_buyer_access'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=new_id)
    organization_id:Mapped[str]=mapped_column(String(36))
    invoice_id:Mapped[str]=mapped_column(String(36))
    token_hash:Mapped[str]=mapped_column(String(64))
    expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
    revoked:Mapped[bool]=mapped_column(Boolean,default=False)
    can_dispute:Mapped[bool]=mapped_column(Boolean,default=True)
    can_promise:Mapped[bool]=mapped_column(Boolean,default=True)
    can_pay:Mapped[bool]=mapped_column(Boolean,default=False,server_default=false())
    view_count:Mapped[int]=mapped_column(Integer,default=0)
    last_viewed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    created_by:Mapped[str]=mapped_column(String(200))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
    __table_args__=(
        ForeignKeyConstraint(['organization_id','invoice_id'],['saas_invoices.organization_id','saas_invoices.id']),
        UniqueConstraint('token_hash'),Index('ix_buyer_access_org_invoice','organization_id','invoice_id'),
    )
