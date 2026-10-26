"""Private, subject-bound, expiring invitations. Raw tokens are never stored."""
from datetime import datetime,timezone

from sqlalchemy import Boolean,DateTime,ForeignKey,Index,String,UniqueConstraint,CheckConstraint
from sqlalchemy.orm import Mapped,mapped_column

from saas_domain import SaaSBase,new_id


class TeamInvitation(SaaSBase):
    __tablename__='saas_team_invitations'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=new_id)
    organization_id:Mapped[str]=mapped_column(String(36),ForeignKey('saas_organizations.id'))
    target_user_id:Mapped[str]=mapped_column(String(200))
    role:Mapped[str]=mapped_column(String(16))
    token_hash:Mapped[str]=mapped_column(String(64))
    expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
    created_by:Mapped[str]=mapped_column(String(200))
    used:Mapped[bool]=mapped_column(Boolean,default=False)
    revoked:Mapped[bool]=mapped_column(Boolean,default=False)
    __table_args__=(UniqueConstraint('token_hash'),Index('ix_invites_org_created','organization_id','created_at'),
        CheckConstraint("role IN ('admin','accountant','viewer')"))
