"""Reviewable recurring invoice draft series."""
import sqlalchemy as sa
from alembic import op

revision='0008_recurring_drafts'
down_revision='0007_invoice_ledger'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('saas_recurring_rules',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('organization_id',sa.String(36),sa.ForeignKey('saas_organizations.id'),nullable=False),
        sa.Column('name',sa.String(100),nullable=False),sa.Column('prefix',sa.String(5),nullable=False),
        sa.Column('frequency',sa.String(8),nullable=False),sa.Column('interval',sa.Integer(),nullable=False),
        sa.Column('anchor_day',sa.Integer(),nullable=False),sa.Column('next_date',sa.Date(),nullable=False),
        sa.Column('end_date',sa.Date(),nullable=True),sa.Column('terms_days',sa.Integer(),nullable=False),
        sa.Column('sequence',sa.Integer(),nullable=False),sa.Column('active',sa.Boolean(),nullable=False),
        sa.Column('template',sa.JSON(),nullable=False),sa.Column('created_by',sa.String(200),nullable=False),
        sa.UniqueConstraint('organization_id','prefix'),sa.CheckConstraint("frequency IN ('weekly','monthly')"),
        sa.CheckConstraint('interval >= 1 AND interval <= 52'),sa.CheckConstraint('anchor_day >= 1 AND anchor_day <= 31'),
        sa.CheckConstraint('terms_days >= 0 AND terms_days <= 365'),sa.CheckConstraint('sequence >= 1 AND sequence <= 10000'))
    if op.get_bind().dialect.name=='postgresql':
        op.execute('ALTER TABLE public.saas_recurring_rules ENABLE ROW LEVEL SECURITY')
        op.execute('REVOKE ALL ON public.saas_recurring_rules FROM anon, authenticated')
        op.execute('GRANT SELECT, INSERT, UPDATE ON public.saas_recurring_rules TO cashpilot_backend')
        op.execute('CREATE POLICY backend_access ON public.saas_recurring_rules FOR ALL TO cashpilot_backend USING (true) WITH CHECK (true)')


def downgrade():op.drop_table('saas_recurring_rules')
