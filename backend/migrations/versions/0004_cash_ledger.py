"""Cash history and plans for financial intelligence.

Revision ID: 0004_cash_ledger
Revises: 0003_backend_runtime_role
"""
import sqlalchemy as sa
from alembic import op

revision = "0004_cash_ledger"
down_revision = "0003_backend_runtime_role"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("saas_cash_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("saas_organizations.id"), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("status", sa.String(8), nullable=False),
        sa.Column("amount_paise", sa.BigInteger(), nullable=False),
        sa.Column("description", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("direction IN ('in', 'out')"),
        sa.CheckConstraint("status IN ('actual', 'planned', 'void')"),
        sa.CheckConstraint("amount_paise > 0 AND amount_paise <= 1000000000000"))
    op.create_index("ix_cash_entries_org_date", "saas_cash_entries", ["organization_id", "entry_date"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE public.saas_cash_entries ENABLE ROW LEVEL SECURITY")
        op.execute("REVOKE ALL ON public.saas_cash_entries FROM anon, authenticated")
        op.execute("GRANT SELECT, INSERT, UPDATE ON public.saas_cash_entries TO cashpilot_backend")
        op.execute("CREATE POLICY cashpilot_backend_access ON public.saas_cash_entries FOR ALL TO cashpilot_backend USING (true) WITH CHECK (true)")
    op.create_index("ix_invoices_org_customer", "saas_invoices", ["organization_id", "customer_id"])
    op.create_index("ix_payments_org_invoice", "saas_payments", ["organization_id", "invoice_id"])


def downgrade():
    op.drop_index("ix_payments_org_invoice", "saas_payments")
    op.drop_index("ix_invoices_org_customer", "saas_invoices")
    op.drop_index("ix_cash_entries_org_date", "saas_cash_entries")
    op.drop_table("saas_cash_entries")
