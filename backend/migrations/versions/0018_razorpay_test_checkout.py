"""Persist sandbox checkout references and private-link payment permission."""
from alembic import op
import sqlalchemy as sa

revision = '0018_razorpay_test_checkout'
down_revision = '0017_collection_tasks'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('saas_buyer_access', sa.Column('can_pay', sa.Boolean(), server_default=sa.false(), nullable=False))
    op.create_table(
        'saas_razorpay_checkouts',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), nullable=False),
        sa.Column('invoice_id', sa.String(36), nullable=False),
        sa.Column('account_id', sa.String(80), nullable=False),
        sa.Column('amount_paise', sa.Integer(), nullable=False),
        sa.Column('expires_at', sa.BigInteger(), nullable=False),
        sa.Column('provider_link_id', sa.String(80), unique=True),
        sa.Column('checkout_url', sa.String(512)),
        sa.Column('provider_payment_id', sa.String(80), unique=True),
        sa.ForeignKeyConstraint(['organization_id', 'invoice_id'], ['saas_invoices.organization_id', 'saas_invoices.id']),
        sa.CheckConstraint('amount_paise BETWEEN 100 AND 2000000000'),
    )
    op.create_index('ix_razorpay_checkout_invoice_expiry', 'saas_razorpay_checkouts',
                    ['organization_id', 'invoice_id', 'expires_at'])
    if op.get_bind().dialect.name == 'postgresql':
        op.execute('ALTER TABLE public.saas_razorpay_checkouts ENABLE ROW LEVEL SECURITY')
        op.execute('REVOKE ALL ON public.saas_razorpay_checkouts FROM PUBLIC, anon, authenticated')
        op.execute('GRANT SELECT, INSERT, UPDATE ON public.saas_razorpay_checkouts TO cashpilot_backend')
        op.execute('CREATE POLICY backend_access ON public.saas_razorpay_checkouts FOR ALL TO cashpilot_backend USING (true) WITH CHECK (true)')


def downgrade():
    op.drop_table('saas_razorpay_checkouts')
    op.drop_column('saas_buyer_access', 'can_pay')
