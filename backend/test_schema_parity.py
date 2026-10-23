"""Ensure Alembic-created schema remains compatible with ORM models."""
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from saas_domain import SaaSBase
import disputes  # noqa: F401
import cash_ledger  # noqa: F401
import audit  # noqa: F401


def test_migration_matches_orm_columns(tmp_path, monkeypatch):
    database = tmp_path / "parity.db"
    url = "sqlite:///" + str(database)
    monkeypatch.setenv("SAAS_DATABASE_URL", url)
    config = Config(str(Path(__file__).with_name("alembic.ini")))
    command.upgrade(config, "head")
    engine = create_engine(url)
    inspector = inspect(engine)
    for name, table in SaaSBase.metadata.tables.items():
        actual = {column["name"] for column in inspector.get_columns(name)}
        expected = set(table.columns.keys())
        assert actual == expected, f"{name}: missing={expected-actual}, extra={actual-expected}"
    engine.dispose()
