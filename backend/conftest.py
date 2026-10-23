"""Keep identity-provider environment and process caches isolated per test."""
import pytest

import auth_identity


@pytest.fixture(autouse=True)
def isolated_identity_provider(monkeypatch):
    # Tests opt into a provider explicitly; developer/staging settings must not
    # change fail-closed assertions or cause a unit test to fetch live JWKS.
    for name in (
        "CASH_PILOT_OIDC_ISSUER",
        "CASH_PILOT_OIDC_AUDIENCE",
        "CASH_PILOT_OIDC_JWKS_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    auth_identity._provider_config.cache_clear()
    auth_identity._jwks_client.cache_clear()
    try:
        yield
    finally:
        # monkeypatch restores environment variables, but cannot undo lru_cache.
        auth_identity._provider_config.cache_clear()
        auth_identity._jwks_client.cache_clear()
