"""Immutable forecast snapshots and actual-record coverage reviews."""
import sqlalchemy as sa
from alembic import op
revision='0013_forecast_journal'
down_revision='0012_contact_preferences'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('saas_forecast_snapshots',sa.Column('id',sa.String(36),primary_key=True),sa.Column('organization_id',sa.String(36),nullable=False),sa.Column('as_of',sa.Date(),nullable=False),sa.Column('request_key',sa.String(80),nullable=False),sa.Column('actor_id',sa.String(200),nullable=False),sa.Column('opening_paise',sa.BigInteger(),nullable=True),sa.Column('threshold_paise',sa.BigInteger(),nullable=False),sa.Column('model_sha256',sa.String(64),nullable=False),sa.Column('input_sha256',sa.String(64),nullable=False),sa.Column('payload',sa.JSON(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.ForeignKeyConstraint(['organization_id'],['saas_organizations.id']),sa.UniqueConstraint('organization_id','id'),sa.UniqueConstraint('organization_id','request_key'),sa.CheckConstraint('threshold_paise >= 0'))
    op.create_index('ix_forecast_snapshots_org_date','saas_forecast_snapshots',['organization_id','as_of'])
    op.create_table('saas_forecast_reviews',sa.Column('id',sa.String(36),primary_key=True),sa.Column('organization_id',sa.String(36),nullable=False),sa.Column('snapshot_id',sa.String(36),nullable=False),sa.Column('horizon_days',sa.Integer(),nullable=False),sa.Column('actual_sha256',sa.String(64),nullable=False),sa.Column('actual_paise',sa.BigInteger(),nullable=False),sa.Column('note',sa.String(1000),nullable=False),sa.Column('actor_id',sa.String(200),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.ForeignKeyConstraint(['organization_id','snapshot_id'],['saas_forecast_snapshots.organization_id','saas_forecast_snapshots.id']),sa.CheckConstraint('horizon_days IN (7,30,90)'))
    op.create_index('ix_forecast_reviews_org_snapshot','saas_forecast_reviews',['organization_id','snapshot_id'])
    if op.get_bind().dialect.name=='postgresql':
        for table in ['saas_forecast_snapshots','saas_forecast_reviews']:
            op.execute(f'ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY')
            op.execute(f'REVOKE ALL ON public.{table} FROM anon, authenticated')
            op.execute(f'GRANT SELECT, INSERT ON public.{table} TO cashpilot_backend')
            op.execute(f'CREATE POLICY backend_access ON public.{table} FOR ALL TO cashpilot_backend USING (true) WITH CHECK (true)')


def downgrade():
    op.drop_table('saas_forecast_reviews');op.drop_table('saas_forecast_snapshots')
