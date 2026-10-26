"""Append-only financial adjustments and records of external refunds."""
import sqlalchemy as sa
from alembic import op

revision = '0007_invoice_ledger'
down_revision = '0006_trade_operations'
branch_labels = None
depends_on = None


def upgrade():
    common = lambda: [sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), nullable=False),
        sa.Column('invoice_id', sa.String(36), nullable=False),
        sa.Column('amount_paise', sa.BigInteger(), nullable=False),
        sa.Column('reason', sa.String(1000), nullable=False),
        sa.Column('actor_id', sa.String(200), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id', 'invoice_id'], ['saas_invoices.organization_id', 'saas_invoices.id']),
        sa.CheckConstraint('amount_paise > 0 AND amount_paise <= 2000000000')]
    op.create_table('saas_invoice_memos', *common(),
        sa.Column('kind', sa.String(8), nullable=False), sa.Column('number', sa.String(16), nullable=False),
        sa.UniqueConstraint('organization_id', 'kind', 'number'), sa.CheckConstraint("kind IN ('credit', 'debit')"))
    op.create_table('saas_invoice_refunds', *common(),
        sa.Column('idempotency_key', sa.String(100), nullable=False),
        sa.UniqueConstraint('organization_id', 'idempotency_key'))
    for table in ['saas_invoice_memos', 'saas_invoice_refunds']:
        op.create_index('ix_' + table + '_org_invoice', table, ['organization_id', 'invoice_id'])
        if op.get_bind().dialect.name == 'postgresql':
            op.execute(f'ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY')
            op.execute(f'REVOKE ALL ON public.{table} FROM anon, authenticated')
            op.execute(f'GRANT SELECT, INSERT ON public.{table} TO cashpilot_backend')
            op.execute(f'CREATE POLICY backend_select ON public.{table} FOR SELECT TO cashpilot_backend USING (true)')
            op.execute(f'CREATE POLICY backend_insert ON public.{table} FOR INSERT TO cashpilot_backend WITH CHECK (true)')


def downgrade():
    op.drop_table('saas_invoice_refunds')
    op.drop_table('saas_invoice_memos')
