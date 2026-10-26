"""Revocable memberships and subject-bound invitations."""
import sqlalchemy as sa
from alembic import op

revision='0009_team_access'
down_revision='0008_recurring_drafts'
branch_labels=None
depends_on=None


def upgrade():
    op.add_column('saas_memberships',sa.Column('active',sa.Boolean(),nullable=False,server_default=sa.true()))
    op.create_table('saas_team_invitations',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('organization_id',sa.String(36),sa.ForeignKey('saas_organizations.id'),nullable=False),
        sa.Column('target_user_id',sa.String(200),nullable=False),sa.Column('role',sa.String(16),nullable=False),
        sa.Column('token_hash',sa.String(64),nullable=False),sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('created_by',sa.String(200),nullable=False),
        sa.Column('used',sa.Boolean(),nullable=False),sa.Column('revoked',sa.Boolean(),nullable=False),
        sa.UniqueConstraint('token_hash'),sa.CheckConstraint("role IN ('admin','accountant','viewer')"))
    op.create_index('ix_invites_org_created','saas_team_invitations',['organization_id','created_at'])
    if op.get_bind().dialect.name=='postgresql':
        op.execute('ALTER TABLE public.saas_team_invitations ENABLE ROW LEVEL SECURITY')
        op.execute('REVOKE ALL ON public.saas_team_invitations FROM anon, authenticated')
        op.execute('GRANT SELECT, INSERT, UPDATE ON public.saas_team_invitations TO cashpilot_backend')
        op.execute('CREATE POLICY backend_access ON public.saas_team_invitations FOR ALL TO cashpilot_backend USING (true) WITH CHECK (true)')


def downgrade():
    op.drop_table('saas_team_invitations')
    op.drop_column('saas_memberships','active')
