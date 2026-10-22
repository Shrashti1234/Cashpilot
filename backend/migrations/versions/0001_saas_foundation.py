"""Initial multi-tenant SaaS domain tables.

Revision ID: 0001_saas_foundation
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_saas_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "saas_organizations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("mode", sa.String(8), nullable=False),
        sa.CheckConstraint("mode IN ('micro', 'b2b')"),
    )
    op.create_table(
        "saas_memberships",
        sa.Column("organization_id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(200), primary_key=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["saas_organizations.id"]),
        sa.CheckConstraint("role IN ('owner', 'admin', 'accountant', 'viewer')"),
    )
    op.create_table(
        "saas_customers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["saas_organizations.id"]),
        sa.UniqueConstraint("organization_id", "id"),
    )
    op.create_table(
        "saas_invoices",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("customer_id", sa.String(36), nullable=False),
        sa.Column("invoice_number", sa.String(64), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("total_paise", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id", "customer_id"],
                                ["saas_customers.organization_id", "saas_customers.id"]),
        sa.UniqueConstraint("organization_id", "invoice_number"),
        sa.UniqueConstraint("organization_id", "id"),
        sa.CheckConstraint("total_paise > 0"),
    )
    op.create_table(
        "saas_payments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("invoice_id", sa.String(36), nullable=False),
        sa.Column("amount_paise", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id", "invoice_id"],
                                ["saas_invoices.organization_id", "saas_invoices.id"]),
        sa.UniqueConstraint("organization_id", "idempotency_key"),
        sa.CheckConstraint("amount_paise > 0"),
    )
    op.create_table(
        "saas_invoice_disputes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("invoice_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(30), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id", "invoice_id"],
                                ["saas_invoices.organization_id", "saas_invoices.id"]),
        sa.UniqueConstraint("organization_id", "invoice_id"),
        sa.CheckConstraint("status IN ('open', 'under_review', 'resolved')"),
        sa.CheckConstraint("reason IN ('amount_mismatch', 'missing_document', 'quality', 'delivery', 'other')"),
    )


def downgrade():
    op.drop_table("saas_invoice_disputes")
    op.drop_table("saas_payments")
    op.drop_table("saas_invoices")
    op.drop_table("saas_customers")
    op.drop_table("saas_memberships")
    op.drop_table("saas_organizations")
