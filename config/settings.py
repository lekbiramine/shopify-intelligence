import os
from dotenv import load_dotenv

load_dotenv()


def _load_shopify_oauth_apps() -> dict[int, tuple[str, str]]:
    """
    Multi-tenant Shopify OAuth: SHOPIFY_APP_1_KEY + SHOPIFY_APP_1_SECRET, etc.
    If none are set, fall back to legacy SHOPIFY_API_KEY / SHOPIFY_API_SECRET as app id 1.
    """
    apps: dict[int, tuple[str, str]] = {}
    for n in range(1, 11):
        key = (os.getenv(f"SHOPIFY_APP_{n}_KEY") or "").strip()
        secret = (os.getenv(f"SHOPIFY_APP_{n}_SECRET") or "").strip()
        if key and secret:
            apps[n] = (key, secret)
    if not apps:
        legacy_key = (os.getenv("SHOPIFY_API_KEY") or "").strip()
        legacy_secret = (os.getenv("SHOPIFY_API_SECRET") or "").strip()
        if legacy_key and legacy_secret:
            apps[1] = (legacy_key, legacy_secret)
    return apps


SHOPIFY_OAUTH_APPS: dict[int, tuple[str, str]] = _load_shopify_oauth_apps()


def get_shopify_oauth_credentials(app_id: int) -> tuple[str, str]:
    """Return (api_key, api_secret) for a configured app index, or raise KeyError."""
    creds = SHOPIFY_OAUTH_APPS.get(int(app_id))
    if not creds:
        raise KeyError(app_id)
    return creds


def get_shopify_oauth_secret_for_api_key(api_key: str) -> str | None:
    """Look up client secret for a stored Shopify API key (client id)."""
    wanted = (api_key or "").strip()
    if not wanted:
        return None
    for _app_id, (k, secret) in SHOPIFY_OAUTH_APPS.items():
        if k == wanted:
            return secret
    return None


def resolve_shopify_oauth_client_credentials(stored_api_key: str | None) -> tuple[str, str]:
    """
    Credentials for token refresh / migration for a store row.
    Uses the store's saved api_key when set; otherwise app id 1 (legacy single-app).
    """
    if (stored_api_key or "").strip():
        secret = get_shopify_oauth_secret_for_api_key(stored_api_key)
        if not secret:
            raise EnvironmentError(
                "Store has api_key set but no matching SHOPIFY_APP_*_KEY/_SECRET in environment."
            )
        return (stored_api_key.strip(), secret)
    if 1 in SHOPIFY_OAUTH_APPS:
        return SHOPIFY_OAUTH_APPS[1]
    raise EnvironmentError(
        "Missing Shopify OAuth credentials: configure SHOPIFY_APP_1_KEY/SECRET "
        "or SHOPIFY_API_KEY/SHOPIFY_API_SECRET, or reinstall stores with app_id."
    )


# Shopify
SHOPIFY_STORE_URL = os.getenv("SHOPIFY_STORE_URL")
SHOPIFY_ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")
SHOPIFY_SCOPES = (
    os.getenv("SHOPIFY_SCOPES")
    or "read_products,read_orders,read_customers,read_inventory"
).strip()
MODAL_TOKEN_ID = (os.getenv("MODAL_TOKEN_ID") or "").strip()
MODAL_TOKEN_SECRET = (os.getenv("MODAL_TOKEN_SECRET") or "").strip()

# Database
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_SSLMODE = os.getenv("DB_SSLMODE", "require").strip().lower()
DB_POOL_MIN = int(os.getenv("DB_POOL_MIN", "1"))
DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "5"))

# Email
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
# The displayed From header can differ from the SMTP login identity.
# Defaults to EMAIL_SENDER for backwards compatibility.
EMAIL_FROM = (os.getenv("EMAIL_FROM") or "").strip() or EMAIL_SENDER
# SMTP username/login (Gmail address). Defaults to EMAIL_SENDER.
SMTP_USERNAME = (os.getenv("SMTP_USERNAME") or "").strip() or EMAIL_SENDER
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USE_SSL = (os.getenv("SMTP_USE_SSL") or "").strip().lower() in {"1", "true", "yes", "on"}
SMTP_USE_STARTTLS = (os.getenv("SMTP_USE_STARTTLS") or "").strip().lower() in {"1", "true", "yes", "on"}
CRON_SECRET = (os.getenv("CRON_SECRET") or "").strip()


def validate_db_env() -> None:
    required = {
        "DB_HOST": DB_HOST,
        "DB_NAME": DB_NAME,
        "DB_USER": DB_USER,
        "DB_PASSWORD": DB_PASSWORD,
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise EnvironmentError(f"Missing required database environment variables: {missing}")
    if DB_SSLMODE not in {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}:
        raise EnvironmentError(f"Invalid DB_SSLMODE: {DB_SSLMODE}")
    if DB_POOL_MIN < 1 or DB_POOL_MAX < DB_POOL_MIN:
        raise EnvironmentError(
            f"Invalid DB pool sizing (DB_POOL_MIN={DB_POOL_MIN}, DB_POOL_MAX={DB_POOL_MAX})"
        )


def validate_shopify_pipeline_env() -> None:
    required_shopify = {
        "SHOPIFY_STORE_URL": SHOPIFY_STORE_URL,
        "SHOPIFY_ACCESS_TOKEN": SHOPIFY_ACCESS_TOKEN,
    }
    missing_shopify = [key for key, value in required_shopify.items() if not value]
    if missing_shopify:
        raise EnvironmentError(
            f"Missing Shopify pipeline environment variables: {missing_shopify}"
        )


def validate_email_env() -> None:
    required_email = {
        "EMAIL_SENDER": EMAIL_SENDER,
        "EMAIL_FROM": EMAIL_FROM,
        "SMTP_USERNAME": SMTP_USERNAME,
        "EMAIL_PASSWORD": EMAIL_PASSWORD,
        "SMTP_HOST": SMTP_HOST,
    }
    missing_email = [key for key, value in required_email.items() if not value]
    if missing_email:
        raise EnvironmentError(
            f"Missing email environment variables: {missing_email}"
        )


def validate_cron_env() -> None:
    required_cron = {
        "CRON_SECRET": CRON_SECRET,
    }
    missing_cron = [key for key, value in required_cron.items() if not value]
    if missing_cron:
        raise EnvironmentError(
            f"Missing cron environment variables: {missing_cron}"
        )


def validate_modal_env() -> None:
    required_modal = {
        "MODAL_TOKEN_ID": MODAL_TOKEN_ID,
        "MODAL_TOKEN_SECRET": MODAL_TOKEN_SECRET,
    }
    missing_modal = [key for key, value in required_modal.items() if not value]
    if missing_modal:
        raise EnvironmentError(
            f"Missing Modal environment variables: {missing_modal}"
        )