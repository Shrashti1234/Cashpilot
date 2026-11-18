"""Contact preferences and append-only completed external contact records."""
import sqlalchemy as sa
from alembic import op
revision='0012_contact_preferences'
down_revision='0011_bank_reconciliation'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('saas_contact_consent_changes',sa.Column('id',sa.String(36),primary_key=True),sa.Column('organization_id',sa.String(36),nullable=False),sa.Column('customer_id',sa.String(36),nullable=False),sa.Column('channel',sa.String(12),nullable=False),sa.Column('status',sa.String(8),nullable=False),sa.Column('evidence',sa.String(1000),nullable=False),sa.Column('expires_on',sa.Date(),nullable=True),sa.Column('actor_id',sa.String(200),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.ForeignKeyConstraint(['organization_id','customer_id'],['saas_customers.organization_id','saas_customers.id']),sa.CheckConstraint("channel IN ('email','whatsapp','phone')"),sa.CheckConstraint("status IN ('granted','revoked','unknown')"))
    op.create_index('ix_consent_changes_org_customer','saas_contact_consent_changes',['organization_id','customer_id'])
    op.create_table('saas_contact_preferences',sa.Column('id',sa.String(36),primary_key=True),sa.Column('organization_id',sa.String(36),nullable=False),sa.Column('customer_id',sa.String(36),nullable=False),sa.Column('channel',sa.String(12),nullable=False),sa.Column('status',sa.String(8),nullable=False),sa.Column('evidence',sa.String(1000),nullable=False),sa.Column('expires_on',sa.Date(),nullable=True),sa.Column('updated_by',sa.String(200),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),sa.ForeignKeyConstraint(['organization_id','customer_id'],['saas_customers.organization_id','saas_customers.id']),sa.UniqueConstraint('organization_id','customer_id','channel'),sa.CheckConstraint("channel IN ('email','whatsapp','phone')"),sa.CheckConstraint("status IN ('granted','revoked','unknown')"))
    op.create_table('saas_contact_records',sa.Column('id',sa.String(36),primary_key=True),sa.Column('organization_id',sa.String(36),nullable=False),sa.Column('customer_id',sa.String(36),nullable=False),sa.Column('invoice_id',sa.String(36),nullable=False),sa.Column('channel',sa.String(12),nullable=False),sa.Column('contact_date',sa.Date(),nullable=False),sa.Column('note',sa.String(1000),nullable=False),sa.Column('actor_id',sa.String(200),nullable=False),sa.Column('request_key',sa.String(80),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.ForeignKeyConstraint(['organization_id','customer_id'],['saas_customers.organization_id','saas_customers.id']),sa.ForeignKeyConstraint(['organization_id','invoice_id'],['saas_invoices.organization_id','saas_invoices.id']),sa.UniqueConstraint('organization_id','request_key'),sa.CheckConstraint("channel IN ('email','whatsapp','phone')"))
    op.create_index('ix_contact_records_org_customer_date','saas_contact_records',['organization_id','customer_id','contact_date'])
    if op.get_bind().dialect.name=='postgresql':
        for table in ['saas_contact_preferences','saas_contact_records','saas_contact_consent_changes']:
            op.execute(f'ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY')
            op.execute(f'REVOKE ALL ON public.{table} FROM anon, authenticated')
            permissions='SELECT, INSERT, UPDATE' if table=='saas_contact_preferences' else 'SELECT, INSERT'
            op.execute(f'GRANT {permissions} ON public.{table} TO cashpilot_backend')
            op.execute(f'CREATE POLICY backend_access ON public.{table} FOR ALL TO cashpilot_backend USING (true) WITH CHECK (true)')


def downgrade():
    op.drop_table('saas_contact_records');op.drop_table('saas_contact_preferences');op.drop_table('saas_contact_consent_changes')
