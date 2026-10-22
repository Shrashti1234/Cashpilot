"""CORS policy tests must not require live PostgreSQL or an identity provider."""
import pytest
from fastapi.testclient import TestClient


def test_cors_origin_validation(monkeypatch):
    from saas_main import allowed_origins
    monkeypatch.setenv("CASH_PILOT_CORS_ORIGINS", "https://cashpilot.example,http://localhost:5173")
    assert allowed_origins() == ["https://cashpilot.example", "http://localhost:5173"]
    monkeypatch.setenv("CASH_PILOT_CORS_ORIGINS", "*")
    with pytest.raises(RuntimeError):
        allowed_origins()
    monkeypatch.setenv("CASH_PILOT_CORS_ORIGINS", "http://untrusted.example")
    with pytest.raises(RuntimeError):
        allowed_origins()
    monkeypatch.setenv("CASH_PILOT_CORS_ORIGINS", "https://cashpilot.example/private")
    with pytest.raises(RuntimeError):
        allowed_origins()


def test_readiness_without_database_returns_503(monkeypatch):
    from fastapi import HTTPException
    from saas_main import app, readiness
    monkeypatch.delattr(app.state, "session_factory", raising=False)
    with pytest.raises(HTTPException) as exc:
        readiness()
    assert exc.value.status_code == 503


def test_readiness_with_database(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from saas_main import app, readiness
    engine = create_engine("sqlite://")
    monkeypatch.setattr(app.state, "session_factory", sessionmaker(bind=engine), raising=False)
    assert readiness()["status"] == "ready"
    engine.dispose()
