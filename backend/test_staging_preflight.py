from staging_preflight import validate_config


def valid_env():
    return {
        "SAAS_DATABASE_URL": "postgresql+psycopg://user:pass@db.example.com:5432/cashpilot",
        "CASH_PILOT_OIDC_ISSUER": "https://auth.example.com/",
        "CASH_PILOT_OIDC_AUDIENCE": "cashpilot-api",
        "CASH_PILOT_OIDC_JWKS_URL": "https://auth.example.com/jwks",
        "CASH_PILOT_CORS_ORIGINS": "https://preview.example.com",
    }


def test_valid_staging_environment():
    assert validate_config(valid_env()) == []


def test_missing_variables_do_not_expose_values():
    errors = validate_config({})
    assert "SAAS_DATABASE_URL" in errors[0]
    assert "pass" not in str(errors)


def test_reject_insecure_oidc_and_wildcard_cors():
    env = valid_env()
    env["CASH_PILOT_OIDC_ISSUER"] = "http://auth.example.com"
    env["CASH_PILOT_CORS_ORIGINS"] = "https://*.example.com"
    errors = validate_config(env)
    assert len(errors) == 2


def test_reject_non_postgresql_database():
    env = valid_env()
    env["SAAS_DATABASE_URL"] = "sqlite:///local.db"
    assert any("postgresql+psycopg" in e for e in validate_config(env))
