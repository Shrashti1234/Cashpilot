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
