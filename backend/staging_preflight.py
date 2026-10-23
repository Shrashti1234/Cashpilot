"""Fail-fast staging configuration checks. Never print secrets or tokens."""
import os
from urllib.parse import urlsplit


REQUIRED = (
    "SAAS_DATABASE_URL",
    "CASH_PILOT_OIDC_ISSUER",
    "CASH_PILOT_OIDC_AUDIENCE",
    "CASH_PILOT_OIDC_JWKS_URL",
    "CASH_PILOT_CORS_ORIGINS",
)


def validate_config(env=None):
    env = os.environ if env is None else env
    missing = [name for name in REQUIRED if not env.get(name, "").strip()]
    if missing:
        return ["Missing: " + ", ".join(missing)]
    errors = []
    database = urlsplit(env["SAAS_DATABASE_URL"])
    if database.scheme != "postgresql+psycopg" or not database.hostname:
        errors.append("SAAS_DATABASE_URL must be a valid postgresql+psycopg URL")
    for name in ("CASH_PILOT_OIDC_ISSUER", "CASH_PILOT_OIDC_JWKS_URL"):
        parsed = urlsplit(env[name])
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            errors.append(name + " must use a valid HTTPS URL")
    if not env["CASH_PILOT_OIDC_AUDIENCE"].strip():
        errors.append("OIDC audience cannot be blank")
    for raw in env["CASH_PILOT_CORS_ORIGINS"].split(","):
        origin = raw.strip()
        parsed = urlsplit(origin)
        if not origin or parsed.scheme != "https" or not parsed.hostname or parsed.path not in ("", "/") or parsed.query or parsed.fragment or parsed.username or parsed.password or "*" in origin:
            errors.append("CORS origins must be explicit HTTPS origins")
            break
    return errors


def main():
    errors = validate_config()
    if errors:
        for error in errors:
            print(error)
        raise SystemExit(1)
    print("Staging configuration syntax checks passed (no connectivity test performed).")


if __name__ == "__main__":
    main()
