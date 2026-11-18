"""Append-only application audit events.

Revision ID: 0005_audit_events
Revises: 0004_cash_ledger
"""
from alembic import op
import sqlalchemy as sa
revision='0005_audit_events'
down_revision='0004_cash_ledger'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('saas_audit_events',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('organization_id',sa.String(36),sa.ForeignKey('saas_organizations.id'),nullable=False),
        sa.Column('actor_id',sa.String(200),nullable=False),
        sa.Column('action',sa.String(60),nullable=False),
        sa.Column('resource_id',sa.String(100),nullable=False),
        sa.Column('occurred_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_audit_org_time','saas_audit_events',['organization_id','occurred_at'])
    if op.get_bind().dialect.name=='postgresql':
        op.execute('ALTER TABLE public.saas_audit_events ENABLE ROW LEVEL SECURITY')
        op.execute('REVOKE ALL ON public.saas_audit_events FROM anon, authenticated')
        op.execute('GRANT SELECT, INSERT ON public.saas_audit_events TO cashpilot_backend')
        op.execute('CREATE POLICY cashpilot_backend_audit_read ON public.saas_audit_events FOR SELECT TO cashpilot_backend USING (true)')
        op.execute('CREATE POLICY cashpilot_backend_audit_insert ON public.saas_audit_events FOR INSERT TO cashpilot_backend WITH CHECK (true)')


def downgrade():
    op.drop_index('ix_audit_org_time','saas_audit_events')
    op.drop_table('saas_audit_events')
