"""Imported statement rows and reversible exact ledger matches."""
import sqlalchemy as sa
from alembic import op
revision='0011_bank_reconciliation'
down_revision='0010_buyer_promises'
branch_labels=None
depends_on=None


def upgrade():
    for table in ['saas_payments','saas_invoice_refunds','saas_cash_entries']:
        op.create_index('uq_'+table+'_org_id',table,['organization_id','id'],unique=True)
    op.create_table('saas_bank_accounts',sa.Column('id',sa.String(36),primary_key=True),sa.Column('organization_id',sa.String(36),nullable=False),sa.Column('label',sa.String(100),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.ForeignKeyConstraint(['organization_id'],['saas_organizations.id']),sa.UniqueConstraint('organization_id','id'),sa.UniqueConstraint('organization_id','label'))
    op.create_table('saas_bank_transactions',sa.Column('id',sa.String(36),primary_key=True),sa.Column('organization_id',sa.String(36),nullable=False),sa.Column('account_id',sa.String(36),nullable=False),sa.Column('booked_date',sa.Date(),nullable=False),sa.Column('reference',sa.String(160),nullable=False),sa.Column('description',sa.String(500),nullable=False),sa.Column('amount_paise',sa.BigInteger(),nullable=False),sa.Column('imported_by',sa.String(200),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.ForeignKeyConstraint(['organization_id','account_id'],['saas_bank_accounts.organization_id','saas_bank_accounts.id']),sa.UniqueConstraint('organization_id','id'),sa.UniqueConstraint('account_id','reference'),sa.CheckConstraint('amount_paise != 0 AND amount_paise BETWEEN -1000000000000 AND 1000000000000'))
    op.create_index('ix_bank_transactions_org_account_date','saas_bank_transactions',['organization_id','account_id','booked_date'])
    op.create_table('saas_bank_matches',sa.Column('id',sa.String(36),primary_key=True),sa.Column('organization_id',sa.String(36),nullable=False),sa.Column('transaction_id',sa.String(36),nullable=False),sa.Column('payment_id',sa.String(36),nullable=True),sa.Column('refund_id',sa.String(36),nullable=True),sa.Column('cash_entry_id',sa.String(36),nullable=True),sa.Column('active',sa.Boolean(),nullable=False),sa.Column('note',sa.String(1000),nullable=False),sa.Column('actor_id',sa.String(200),nullable=False),sa.Column('reversal_reason',sa.String(1000),nullable=True),sa.Column('reversed_by',sa.String(200),nullable=True),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        *[sa.ForeignKeyConstraint(['organization_id',column],[table+'.organization_id',table+'.id']) for column,table in [('transaction_id','saas_bank_transactions'),('payment_id','saas_payments'),('refund_id','saas_invoice_refunds'),('cash_entry_id','saas_cash_entries')]],
        sa.CheckConstraint('(CASE WHEN payment_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN refund_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN cash_entry_id IS NOT NULL THEN 1 ELSE 0 END) = 1'))
    for column in ['transaction_id','payment_id','refund_id','cash_entry_id']:
        op.create_index('uq_bank_match_active_'+column,'saas_bank_matches',['organization_id',column],unique=True,postgresql_where=sa.text('active = true'),sqlite_where=sa.text('active = 1'))
    if op.get_bind().dialect.name=='postgresql':
        for table in ['saas_bank_accounts','saas_bank_transactions','saas_bank_matches']:
            op.execute(f'ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY')
            op.execute(f'REVOKE ALL ON public.{table} FROM anon, authenticated')
            permissions='SELECT, INSERT, UPDATE' if table=='saas_bank_matches' else 'SELECT, INSERT'
            op.execute(f'GRANT {permissions} ON public.{table} TO cashpilot_backend')
            op.execute(f'CREATE POLICY backend_access ON public.{table} FOR ALL TO cashpilot_backend USING (true) WITH CHECK (true)')


def downgrade():
    for table in ['saas_bank_matches','saas_bank_transactions','saas_bank_accounts']:op.drop_table(table)
    for table in ['saas_payments','saas_invoice_refunds','saas_cash_entries']:
        op.drop_index('uq_'+table+'_org_id',table_name=table)
