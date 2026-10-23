"""Production-oriented OIDC bearer verification.

Set CASH_PILOT_OIDC_ISSUER, CASH_PILOT_OIDC_AUDIENCE and
CASH_PILOT_OIDC_JWKS_URL from the selected identity provider's documentation.
Never derive identity from a request header supplied by the browser.
"""
from functools import lru_cache
import os

import jwt
from fastapi import HTTPException, Request
from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError, PyJWKClientError


@lru_cache(maxsize=1)
def _provider_config() -> tuple[str, str, str]:
    issuer = os.getenv("CASH_PILOT_OIDC_ISSUER", "").strip()
    audience = os.getenv("CASH_PILOT_OIDC_AUDIENCE", "").strip()
    jwks_url = os.getenv("CASH_PILOT_OIDC_JWKS_URL", "").strip()
    if not issuer.startswith("https://") or not audience or not jwks_url.startswith("https://"):
        raise RuntimeError("OIDC issuer, audience and JWKS URL must be configured with HTTPS")
    return issuer, audience, jwks_url


@lru_cache(maxsize=4)
def _jwks_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url, cache_jwk_set=True, lifespan=300, timeout=5)


def verify_bearer_token(token: str) -> str:
    issuer, audience, jwks_url = _provider_config()
    try:
        key = _jwks_client(jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token, key.key, algorithms=["RS256", "ES256"], audience=audience, issuer=issuer,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            leeway=30,
        )
    except (InvalidTokenError, PyJWKClientError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid authentication token") from exc
    if issuer.endswith(".supabase.co/auth/v1") and claims.get("role") != "authenticated":
        raise HTTPException(status_code=401, detail="Authenticated user token required")
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        raise HTTPException(status_code=401, detail="Invalid authentication subject")
    return subject


def get_verified_identity(request: Request) -> str:
    try:
        _provider_config()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Authentication provider not configured") from exc
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Bearer token required")
    return verify_bearer_token(token.strip())
