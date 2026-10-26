"""Independent financial request approval policy and review queue."""
import sqlalchemy as sa
from alembic import op
revision='0014_financial_approvals'
down_revision='0013_forecast_journal'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('saas_financial_policies',sa.Column('organization_id',sa.String(36),primary_key=True),sa.Column('require_approval',sa.Boolean(),nullable=False),sa.Column('updated_by',sa.String(200),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),sa.ForeignKeyConstraint(['organization_id'],['saas_organizations.id']))
    op.create_table('saas_financial_approvals',sa.Column('id',sa.String(36),primary_key=True),sa.Column('organization_id',sa.String(36),nullable=False),sa.Column('invoice_id',sa.String(36),nullable=False),sa.Column('operation',sa.String(16),nullable=False),sa.Column('payload',sa.JSON(),nullable=False),sa.Column('status',sa.String(12),nullable=False),sa.Column('requested_by',sa.String(200),nullable=False),sa.Column('request_key',sa.String(80),nullable=False),sa.Column('decided_by',sa.String(200),nullable=True),sa.Column('decision_note',sa.String(1000),nullable=True),sa.Column('decided_at',sa.DateTime(timezone=True),nullable=True),sa.Column('posted_id',sa.String(36),nullable=True),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.ForeignKeyConstraint(['organization_id','invoice_id'],['saas_invoices.organization_id','saas_invoices.id']),sa.UniqueConstraint('organization_id','request_key'),sa.CheckConstraint("operation IN ('memo','refund_record')"),sa.CheckConstraint("status IN ('pending','approved','rejected','cancelled')"),sa.CheckConstraint("(status = 'approved' AND posted_id IS NOT NULL) OR (status != 'approved' AND posted_id IS NULL)"))
    op.create_index('ix_financial_approvals_org_status','saas_financial_approvals',['organization_id','status','created_at'])
    if op.get_bind().dialect.name=='postgresql':
        for table in ['saas_financial_policies','saas_financial_approvals']:
            op.execute(f'ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY')
            op.execute(f'REVOKE ALL ON public.{table} FROM anon, authenticated')
            op.execute(f'GRANT SELECT, INSERT ON public.{table} TO cashpilot_backend')
            columns='require_approval,updated_by,updated_at' if table=='saas_financial_policies' else 'status,decided_by,decision_note,decided_at,posted_id'
            op.execute(f'GRANT UPDATE ({columns}) ON public.{table} TO cashpilot_backend')
            op.execute(f'CREATE POLICY backend_access ON public.{table} FOR ALL TO cashpilot_backend USING (true) WITH CHECK (true)')


def downgrade():
    op.drop_table('saas_financial_approvals');op.drop_table('saas_financial_policies')
