from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from jwt.algorithms import RSAAlgorithm

import auth_identity


@pytest.fixture
def keys(monkeypatch):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key()
    monkeypatch.setenv("CASH_PILOT_OIDC_ISSUER", "https://login.example.test/")
    monkeypatch.setenv("CASH_PILOT_OIDC_AUDIENCE", "cashpilot-api")
    monkeypatch.setenv("CASH_PILOT_OIDC_JWKS_URL", "https://login.example.test/keys")
    auth_identity._provider_config.cache_clear()
    return private, public


def make_token(private, **overrides):
    now = datetime.now(timezone.utc)
    payload = {"sub": "user-123", "iss": "https://login.example.test/",
               "aud": "cashpilot-api", "iat": now, "exp": now + timedelta(minutes=10)}
    payload.update(overrides)
    return jwt.encode(payload, private, algorithm="RS256", headers={"kid": "test-key"})


def test_valid_signature_and_claims(keys):
    private, public = keys
    class FakeJwks:
        def get_signing_key_from_jwt(self, token):
            return type("Key", (), {"key": public})()
    with patch.object(auth_identity, "_jwks_client", return_value=FakeJwks()):
        assert auth_identity.verify_bearer_token(make_token(private)) == "user-123"


def test_wrong_audience_rejected(keys):
    private, public = keys
    class FakeJwks:
        def get_signing_key_from_jwt(self, token):
            return type("Key", (), {"key": public})()
    with patch.object(auth_identity, "_jwks_client", return_value=FakeJwks()):
        with pytest.raises(HTTPException) as err:
            auth_identity.verify_bearer_token(make_token(private, aud="other"))
        assert err.value.status_code == 401


def test_expired_token_rejected(keys):
    private, public = keys
    class FakeJwks:
        def get_signing_key_from_jwt(self, token):
            return type("Key", (), {"key": public})()
    with patch.object(auth_identity, "_jwks_client", return_value=FakeJwks()):
        with pytest.raises(HTTPException) as err:
            auth_identity.verify_bearer_token(make_token(
                private, exp=datetime.now(timezone.utc) - timedelta(minutes=5)))
        assert err.value.status_code == 401


def test_unconfigured_provider_fails_closed(monkeypatch):
    monkeypatch.delenv("CASH_PILOT_OIDC_ISSUER", raising=False)
    auth_identity._provider_config.cache_clear()
    with pytest.raises(RuntimeError):
        auth_identity._provider_config()


@pytest.mark.parametrize("path", [
    "/api/v1/organizations",
    "/api/v1/organizations/a/invoices",
])
def test_configured_provider_still_requires_bearer_token(keys, path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from organizations_api import router as organizations_router
    from saas_api import router as saas_router

    app = FastAPI()
    app.include_router(organizations_router)
    app.include_router(saas_router)
    with TestClient(app) as client:
        response = client.get(path)
    assert response.status_code == 401
    assert response.json()["detail"] == "Bearer token required"


def test_supabase_es256_requires_authenticated_role(monkeypatch):
    from cryptography.hazmat.primitives.asymmetric import ec
    private = ec.generate_private_key(ec.SECP256R1())
    public = private.public_key()
    issuer = "https://example.supabase.co/auth/v1"
    monkeypatch.setenv("CASH_PILOT_OIDC_ISSUER", issuer)
    monkeypatch.setenv("CASH_PILOT_OIDC_AUDIENCE", "authenticated")
    monkeypatch.setenv("CASH_PILOT_OIDC_JWKS_URL", issuer + "/.well-known/jwks.json")
    auth_identity._provider_config.cache_clear()
    now = datetime.now(timezone.utc)
    payload = {"sub": "user-123", "iss": issuer, "aud": "authenticated",
               "iat": now, "exp": now + timedelta(minutes=10), "role": "authenticated"}
    class FakeJwks:
        def get_signing_key_from_jwt(self, token):
            return type("Key", (), {"key": public})()
    with patch.object(auth_identity, "_jwks_client", return_value=FakeJwks()):
        valid = jwt.encode(payload, private, algorithm="ES256", headers={"kid": "test-key"})
        assert auth_identity.verify_bearer_token(valid) == "user-123"
        payload["role"] = "anon"
        invalid = jwt.encode(payload, private, algorithm="ES256", headers={"kid": "test-key"})
        with pytest.raises(HTTPException) as err:
            auth_identity.verify_bearer_token(invalid)
        assert err.value.status_code == 401
