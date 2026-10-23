"""Least-privilege database access for the trusted FastAPI runtime.

Revision ID: 0003_backend_runtime_role
Revises: 0002_supabase_access

Credentials are provisioned separately through secure platform configuration.
This role is never granted to PostgREST/browser roles. FastAPI still enforces
JWT identity and organization membership on every business-data request.
"""
from alembic import op

revision = "0003_backend_runtime_role"
down_revision = "0002_supabase_access"
branch_labels = None
depends_on = None

TABLES = (
    "saas_organizations", "saas_memberships", "saas_customers",
    "saas_invoices", "saas_payments", "saas_invoice_disputes",
)


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cashpilot_backend') THEN
                CREATE ROLE cashpilot_backend NOLOGIN NOSUPERUSER NOCREATEDB
                    NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 10;
            END IF;
        END $$;
    """)
    op.execute("GRANT USAGE ON SCHEMA public TO cashpilot_backend")
    for table in TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON public.{table} TO cashpilot_backend")
        # Only the trusted service role can use this policy. Browser database
        # privileges remain revoked by 0002; no global RLS bypass is granted.
        op.execute(f"CREATE POLICY cashpilot_backend_access ON public.{table} "
                   "FOR ALL TO cashpilot_backend USING (true) WITH CHECK (true)")
    op.execute("GRANT SELECT ON public.alembic_version TO cashpilot_backend")
    op.execute("CREATE POLICY cashpilot_backend_revision ON public.alembic_version "
               "FOR SELECT TO cashpilot_backend USING (true)")


def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in TABLES:
        op.execute(f"DROP POLICY IF EXISTS cashpilot_backend_access ON public.{table}")
        op.execute(f"REVOKE ALL ON public.{table} FROM cashpilot_backend")
    op.execute("DROP POLICY IF EXISTS cashpilot_backend_revision ON public.alembic_version")
    op.execute("REVOKE ALL ON public.alembic_version FROM cashpilot_backend")
    # Retain the runtime role and its external credential; do not drop a role
    # that may be referenced by operational connections or other grants.
