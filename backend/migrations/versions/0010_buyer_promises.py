"""Invoice-scoped private buyer access and payment promises."""
import sqlalchemy as sa
from alembic import op

revision='0010_buyer_promises'
down_revision='0009_team_access'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('saas_buyer_access',
        sa.Column('id',sa.String(36),primary_key=True),sa.Column('organization_id',sa.String(36),nullable=False),
        sa.Column('invoice_id',sa.String(36),nullable=False),sa.Column('token_hash',sa.String(64),nullable=False),
        sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),sa.Column('revoked',sa.Boolean(),nullable=False),
        sa.Column('can_dispute',sa.Boolean(),nullable=False),sa.Column('can_promise',sa.Boolean(),nullable=False),
        sa.Column('view_count',sa.Integer(),nullable=False),sa.Column('last_viewed_at',sa.DateTime(timezone=True),nullable=True),
        sa.Column('created_by',sa.String(200),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.ForeignKeyConstraint(['organization_id','invoice_id'],['saas_invoices.organization_id','saas_invoices.id']),
        sa.UniqueConstraint('token_hash'))
    op.create_index('ix_buyer_access_org_invoice','saas_buyer_access',['organization_id','invoice_id'])
    op.create_table('saas_payment_promises',
        sa.Column('id',sa.String(36),primary_key=True),sa.Column('organization_id',sa.String(36),nullable=False),
        sa.Column('invoice_id',sa.String(36),nullable=False),sa.Column('amount_paise',sa.BigInteger(),nullable=False),
        sa.Column('promised_date',sa.Date(),nullable=False),sa.Column('note',sa.String(1000),nullable=False),
        sa.Column('status',sa.String(12),nullable=False),sa.Column('cancellation_note',sa.String(1000),nullable=True),
        sa.Column('actor_id',sa.String(200),nullable=False),sa.Column('request_key',sa.String(100),nullable=False),
        sa.Column('source',sa.String(12),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.ForeignKeyConstraint(['organization_id','invoice_id'],['saas_invoices.organization_id','saas_invoices.id']),
        sa.UniqueConstraint('organization_id','request_key'),sa.CheckConstraint('amount_paise > 0 AND amount_paise <= 2000000000'),
        sa.CheckConstraint("status IN ('pending','fulfilled','cancelled')"),sa.CheckConstraint("source IN ('member','buyer_link')"))
    op.create_index('ix_promises_org_invoice','saas_payment_promises',['organization_id','invoice_id'])
    op.create_index('uq_promises_pending_invoice','saas_payment_promises',['organization_id','invoice_id'],unique=True,
        postgresql_where=sa.text("status='pending'"),sqlite_where=sa.text("status='pending'"))
    if op.get_bind().dialect.name=='postgresql':
        for table in ['saas_buyer_access','saas_payment_promises']:
            op.execute(f'ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY')
            op.execute(f'REVOKE ALL ON public.{table} FROM anon, authenticated')
            op.execute(f'GRANT SELECT, INSERT, UPDATE ON public.{table} TO cashpilot_backend')
            op.execute(f'CREATE POLICY backend_access ON public.{table} FOR ALL TO cashpilot_backend USING (true) WITH CHECK (true)')


def downgrade():
    op.drop_table('saas_payment_promises')
    op.drop_table('saas_buyer_access')
