"""Protect source document snapshots with column-level runtime privileges."""
from alembic import op
revision='0015_document_snapshot_grants'
down_revision='0014_financial_approvals'
branch_labels=None
depends_on=None


def upgrade():
    if op.get_bind().dialect.name=='postgresql':
        op.execute('REVOKE UPDATE ON public.saas_trade_documents FROM cashpilot_backend')
        op.execute('GRANT UPDATE (status,approved_by,invoice_id,received) ON public.saas_trade_documents TO cashpilot_backend')


def downgrade():
    if op.get_bind().dialect.name=='postgresql':
        op.execute('REVOKE UPDATE (status,approved_by,invoice_id,received) ON public.saas_trade_documents FROM cashpilot_backend')
        op.execute('GRANT UPDATE ON public.saas_trade_documents TO cashpilot_backend')
