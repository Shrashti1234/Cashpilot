"""Restrict Supabase Data API exposure for server-owned SaaS tables.

Revision ID: 0002_supabase_access
Revises: 0001_saas_foundation
"""
from alembic import op

revision = "0002_supabase_access"
down_revision = "0001_saas_foundation"
branch_labels = None
depends_on = None

TABLES = (
    "saas_organizations",
    "saas_memberships",
    "saas_customers",
    "saas_invoices",
    "saas_payments",
    "saas_invoice_disputes",
)


def upgrade():
    # SQLite is used only for local schema parity tests; RLS is PostgreSQL-specific.
    if op.get_bind().dialect.name != "postgresql":
        return
    # FastAPI performs identity verification and tenant authorization.
    # Do not grant direct PostgREST access until tenant-specific policies exist.
    for table in TABLES:
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON TABLE public.{table} FROM anon, authenticated")
    op.execute("ALTER TABLE public.alembic_version ENABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON TABLE public.alembic_version FROM anon, authenticated")


def downgrade():
    # Security settings are deliberately retained on downgrade.
    # Disabling RLS or restoring public grants would expose tenant data.
    pass
