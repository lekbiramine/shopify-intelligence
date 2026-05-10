import os
from dotenv import load_dotenv

load_dotenv()

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