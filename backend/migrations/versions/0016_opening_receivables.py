"""Distinguish imported opening balances from newly issued invoices."""
from alembic import op
import sqlalchemy as sa

revision = '0016_opening_receivables'
down_revision = '0015_document_snapshot_grants'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('saas_invoices', sa.Column('opening_receivable', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column('saas_invoices', 'opening_receivable')
