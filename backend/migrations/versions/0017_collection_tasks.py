"""Persist tenant-scoped follow-up ownership."""
from alembic import op
import sqlalchemy as sa

revision = '0017_collection_tasks'
down_revision = '0016_opening_receivables'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('saas_collection_tasks',
        sa.Column('organization_id', sa.String(36), primary_key=True),
        sa.Column('invoice_id', sa.String(36), primary_key=True),
        sa.Column('assignee', sa.String(200), nullable=False),
        sa.Column('follow_up', sa.Date(), nullable=False),
        sa.Column('note', sa.String(500), nullable=False),
        sa.ForeignKeyConstraint(['organization_id', 'invoice_id'], ['saas_invoices.organization_id', 'saas_invoices.id']),
        sa.ForeignKeyConstraint(['organization_id', 'assignee'], ['saas_memberships.organization_id', 'saas_memberships.user_id']))
    if op.get_bind().dialect.name == 'postgresql':
        op.execute('ALTER TABLE public.saas_collection_tasks ENABLE ROW LEVEL SECURITY')
        op.execute('REVOKE ALL ON public.saas_collection_tasks FROM PUBLIC, anon, authenticated')
        op.execute('GRANT SELECT, INSERT, UPDATE ON public.saas_collection_tasks TO cashpilot_backend')
        op.execute('CREATE POLICY backend_access ON public.saas_collection_tasks FOR ALL TO cashpilot_backend USING (true) WITH CHECK (true)')


def downgrade():
    op.drop_table('saas_collection_tasks')
