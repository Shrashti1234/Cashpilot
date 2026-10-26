"""Catalogue, append-only stock and financial document snapshots.

Revision ID: 0006_trade_operations
Revises: 0005_audit_events
"""
import sqlalchemy as sa
from alembic import op

revision = '0006_trade_operations'
down_revision = '0005_audit_events'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('saas_business_profiles',
        sa.Column('organization_id', sa.String(36), primary_key=True),
        sa.Column('legal_name', sa.String(160), nullable=False),
        sa.Column('address', sa.String(1000), nullable=False),
        sa.Column('gstin', sa.String(15), nullable=False),
        sa.Column('state_code', sa.String(2), nullable=False),
        sa.Column('require_approval', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['saas_organizations.id']))
    op.create_table('saas_products',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), nullable=False),
        sa.Column('sku', sa.String(60), nullable=False),
        sa.Column('name', sa.String(160), nullable=False),
        sa.Column('unit', sa.String(16), nullable=False),
        sa.Column('hsn_sac', sa.String(8), nullable=False),
        sa.Column('unit_price_paise', sa.BigInteger(), nullable=False),
        sa.Column('tax_rate_bps', sa.BigInteger(), nullable=False),
        sa.Column('track_stock', sa.Boolean(), nullable=False),
        sa.Column('reorder_milliunits', sa.BigInteger(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['saas_organizations.id']),
        sa.UniqueConstraint('organization_id', 'id'),
        sa.UniqueConstraint('organization_id', 'sku'),
        sa.CheckConstraint('unit_price_paise >= 0 AND unit_price_paise <= 1000000000'),
        sa.CheckConstraint('tax_rate_bps >= 0 AND tax_rate_bps <= 10000'),
        sa.CheckConstraint('reorder_milliunits >= 0'))
    op.create_table('saas_stock_movements',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), nullable=False),
        sa.Column('product_id', sa.String(36), nullable=False),
        sa.Column('quantity_milliunits', sa.BigInteger(), nullable=False),
        sa.Column('reason', sa.String(20), nullable=False),
        sa.Column('reference', sa.String(160), nullable=False),
        sa.Column('request_key', sa.String(100), nullable=False),
        sa.Column('actor_id', sa.String(200), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id', 'product_id'], ['saas_products.organization_id', 'saas_products.id']),
        sa.UniqueConstraint('organization_id', 'request_key'),
        sa.CheckConstraint('quantity_milliunits != 0'),
        sa.CheckConstraint("reason IN ('opening', 'adjustment', 'purchase_receipt', 'invoice_issue')"))
    op.create_index('ix_stock_org_product', 'saas_stock_movements', ['organization_id', 'product_id'])
    op.create_table('saas_trade_documents',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('number', sa.String(16), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('customer_id', sa.String(36), nullable=True),
        sa.Column('invoice_id', sa.String(36), nullable=True),
        sa.Column('issue_date', sa.Date(), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column('party', sa.JSON(), nullable=False),
        sa.Column('supplier', sa.JSON(), nullable=False),
        sa.Column('lines', sa.JSON(), nullable=False),
        sa.Column('totals', sa.JSON(), nullable=False),
        sa.Column('received', sa.JSON(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=False),
        sa.Column('created_by', sa.String(200), nullable=False),
        sa.Column('approved_by', sa.String(200), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['saas_organizations.id']),
        sa.ForeignKeyConstraint(['organization_id', 'customer_id'], ['saas_customers.organization_id', 'saas_customers.id']),
        sa.ForeignKeyConstraint(['organization_id', 'invoice_id'], ['saas_invoices.organization_id', 'saas_invoices.id']),
        sa.UniqueConstraint('organization_id', 'kind', 'number'),
        sa.CheckConstraint("kind IN ('estimate', 'purchase_order', 'invoice')"),
        sa.CheckConstraint("status IN ('draft', 'approved', 'issued', 'cancelled')"))
    op.create_index('ix_documents_org_created', 'saas_trade_documents', ['organization_id', 'created_at'])
    if op.get_bind().dialect.name == 'postgresql':
        for table in ['saas_business_profiles', 'saas_products', 'saas_stock_movements', 'saas_trade_documents']:
            op.execute(f'ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY')
            op.execute(f'REVOKE ALL ON public.{table} FROM anon, authenticated')
            privileges = 'SELECT, INSERT' if table == 'saas_stock_movements' else 'SELECT, INSERT, UPDATE'
            op.execute(f'GRANT {privileges} ON public.{table} TO cashpilot_backend')
            for command in (['SELECT', 'INSERT'] if table == 'saas_stock_movements' else ['SELECT', 'INSERT', 'UPDATE']):
                using = ' USING (true)' if command in {'SELECT', 'UPDATE'} else ''
                check = ' WITH CHECK (true)' if command in {'INSERT', 'UPDATE'} else ''
                op.execute(f'CREATE POLICY backend_{command.lower()} ON public.{table} FOR {command} TO cashpilot_backend{using}{check}')


def downgrade():
    for table in ['saas_trade_documents', 'saas_stock_movements', 'saas_products', 'saas_business_profiles']:
        op.drop_table(table)
