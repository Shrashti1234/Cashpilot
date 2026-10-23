"""Migration smoke test against isolated SQLite database."""
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_initial_migration_creates_and_reverts_saas_tables(tmp_path, monkeypatch):
    database = tmp_path / "migration.db"
    monkeypatch.setenv("SAAS_DATABASE_URL", "sqlite:///" + str(database))
    config = Config(str(Path(__file__).with_name("alembic.ini")))
    command.upgrade(config, "head")
    engine = create_engine("sqlite:///" + str(database))
    tables = set(inspect(engine).get_table_names())
    assert {"saas_organizations", "saas_memberships", "saas_customers",
            "saas_invoices", "saas_payments", "saas_invoice_disputes"} <= tables
    engine.dispose()
    command.downgrade(config, "base")
    engine = create_engine("sqlite:///" + str(database))
    assert "saas_organizations" not in inspect(engine).get_table_names()
    engine.dispose()
