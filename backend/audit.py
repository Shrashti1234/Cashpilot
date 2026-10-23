"""Minimal append-only application audit trail; no tokens or request payloads."""
from datetime import datetime,timezone
from uuid import uuid4
from sqlalchemy import DateTime,ForeignKey,Index,String
from sqlalchemy.orm import Mapped,mapped_column
from saas_domain import SaaSBase


class AuditEvent(SaaSBase):
    __tablename__='saas_audit_events'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid4()))
    organization_id:Mapped[str]=mapped_column(String(36),ForeignKey('saas_organizations.id'),nullable=False)
    actor_id:Mapped[str]=mapped_column(String(200),nullable=False)
    action:Mapped[str]=mapped_column(String(60),nullable=False)
    resource_id:Mapped[str]=mapped_column(String(100),nullable=False)
    occurred_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
    __table_args__=(Index('ix_audit_org_time','organization_id','occurred_at'),)


def record_event(db,organization_id,actor_id,action,resource_id):
    db.add(AuditEvent(organization_id=organization_id,actor_id=actor_id,action=action,resource_id=str(resource_id)))
