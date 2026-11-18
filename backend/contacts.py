"""Business-recorded contact consent and completed external contact history."""
from datetime import date,datetime,timezone
from sqlalchemy import Date,DateTime,ForeignKeyConstraint,Index,String,UniqueConstraint,CheckConstraint,select,func
from sqlalchemy.orm import Mapped,mapped_column
from saas_domain import SaaSBase,new_id


class ContactPreference(SaaSBase):
    __tablename__='saas_contact_preferences'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=new_id)
    organization_id:Mapped[str]=mapped_column(String(36))
    customer_id:Mapped[str]=mapped_column(String(36))
    channel:Mapped[str]=mapped_column(String(12))
    status:Mapped[str]=mapped_column(String(8))
    evidence:Mapped[str]=mapped_column(String(1000))
    expires_on:Mapped[date|None]=mapped_column(Date,nullable=True)
    updated_by:Mapped[str]=mapped_column(String(200))
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
    __table_args__=(ForeignKeyConstraint(['organization_id','customer_id'],['saas_customers.organization_id','saas_customers.id']),UniqueConstraint('organization_id','customer_id','channel'),CheckConstraint("channel IN ('email','whatsapp','phone')"),CheckConstraint("status IN ('granted','revoked','unknown')"))


class ContactRecord(SaaSBase):
    __tablename__='saas_contact_records'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=new_id)
    organization_id:Mapped[str]=mapped_column(String(36))
    customer_id:Mapped[str]=mapped_column(String(36))
    invoice_id:Mapped[str]=mapped_column(String(36))
    channel:Mapped[str]=mapped_column(String(12))
    contact_date:Mapped[date]=mapped_column(Date)
    note:Mapped[str]=mapped_column(String(1000))
    actor_id:Mapped[str]=mapped_column(String(200))
    request_key:Mapped[str]=mapped_column(String(80))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
    __table_args__=(ForeignKeyConstraint(['organization_id','customer_id'],['saas_customers.organization_id','saas_customers.id']),ForeignKeyConstraint(['organization_id','invoice_id'],['saas_invoices.organization_id','saas_invoices.id']),UniqueConstraint('organization_id','request_key'),CheckConstraint("channel IN ('email','whatsapp','phone')"),Index('ix_contact_records_org_customer_date','organization_id','customer_id','contact_date'))


def last_contacts(db,org):
    return dict(db.execute(select(ContactRecord.customer_id,func.max(ContactRecord.contact_date)).where(ContactRecord.organization_id==org).group_by(ContactRecord.customer_id)).all())


class ContactConsentChange(SaaSBase):
    __tablename__='saas_contact_consent_changes'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=new_id)
    organization_id:Mapped[str]=mapped_column(String(36))
    customer_id:Mapped[str]=mapped_column(String(36))
    channel:Mapped[str]=mapped_column(String(12))
    status:Mapped[str]=mapped_column(String(8))
    evidence:Mapped[str]=mapped_column(String(1000))
    expires_on:Mapped[date|None]=mapped_column(Date,nullable=True)
    actor_id:Mapped[str]=mapped_column(String(200))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
    __table_args__=(ForeignKeyConstraint(['organization_id','customer_id'],['saas_customers.organization_id','saas_customers.id']),Index('ix_consent_changes_org_customer','organization_id','customer_id'),CheckConstraint("channel IN ('email','whatsapp','phone')"),CheckConstraint("status IN ('granted','revoked','unknown')"))
