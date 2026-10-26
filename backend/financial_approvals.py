"""Independent review of internal memos and completed external refund records."""
from datetime import datetime,timezone
from fastapi import HTTPException
from sqlalchemy import Boolean,CheckConstraint,DateTime,ForeignKey,ForeignKeyConstraint,Index,JSON,String,UniqueConstraint,select
from sqlalchemy.orm import Mapped,mapped_column
from saas_domain import SaaSBase,Membership,new_id,lock_organization


class FinancialPolicy(SaaSBase):
    __tablename__='saas_financial_policies'
    organization_id:Mapped[str]=mapped_column(String(36),ForeignKey('saas_organizations.id'),primary_key=True)
    require_approval:Mapped[bool]=mapped_column(Boolean,default=False)
    updated_by:Mapped[str]=mapped_column(String(200))
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))


class FinancialApproval(SaaSBase):
    __tablename__='saas_financial_approvals'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=new_id)
    organization_id:Mapped[str]=mapped_column(String(36))
    invoice_id:Mapped[str]=mapped_column(String(36))
    operation:Mapped[str]=mapped_column(String(16))
    payload:Mapped[dict]=mapped_column(JSON)
    status:Mapped[str]=mapped_column(String(12),default='pending')
    requested_by:Mapped[str]=mapped_column(String(200))
    request_key:Mapped[str]=mapped_column(String(80))
    decided_by:Mapped[str|None]=mapped_column(String(200),nullable=True)
    decision_note:Mapped[str|None]=mapped_column(String(1000),nullable=True)
    decided_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    posted_id:Mapped[str|None]=mapped_column(String(36),nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
    __table_args__=(ForeignKeyConstraint(['organization_id','invoice_id'],['saas_invoices.organization_id','saas_invoices.id']),UniqueConstraint('organization_id','request_key'),CheckConstraint("operation IN ('memo','refund_record')"),CheckConstraint("status IN ('pending','approved','rejected','cancelled')"),CheckConstraint("(status = 'approved' AND posted_id IS NOT NULL) OR (status != 'approved' AND posted_id IS NULL)"),Index('ix_financial_approvals_org_status','organization_id','status','created_at'))


def locked_writer(db,org,actor,admin=False,owner=False):
    lock_organization(db,org)
    membership=db.scalar(select(Membership).where(Membership.organization_id==org,Membership.user_id==actor).execution_options(populate_existing=True))
    if not membership or not membership.active or membership.role=='viewer' or admin and membership.role not in {'owner','admin'} or owner and membership.role!='owner':raise HTTPException(403,'Forbidden')
    return membership


def guard_direct_post(db,org,actor,admin=False):
    locked_writer(db,org,actor,admin=admin)
    policy=db.get(FinancialPolicy,org,populate_existing=True)
    if policy and policy.require_approval:raise ValueError('Independent financial approval is required. Submit this record through Financial approvals.')
