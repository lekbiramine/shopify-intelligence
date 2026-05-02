import os
from dotenv import load_dotenv

load_dotenv()

# Shopify
SHOPIFY_STORE_URL = os.getenv("SHOPIFY_STORE_URL")
SHOPIFY_ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")

# Database
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

# Email
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECIPIENT = os.getenv("EMAIL_RECIPIENT")
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))

# Optional CC on every store intelligence report email. If unset, copies lekbiramine09@gmail.com.
# Set to empty (STORE_REPORT_CC_EMAIL=) to disable; set to another address to override.
_raw_store_report_cc = os.getenv("STORE_REPORT_CC_EMAIL")
if _raw_store_report_cc is None:
    STORE_REPORT_CC_EMAIL = "lekbiramine09@gmail.com"
else:
    STORE_REPORT_CC_EMAIL = _raw_store_report_cc.strip() or None

# Validation
required = {
    "DB_HOST": DB_HOST,
    "DB_NAME": DB_NAME,
    "DB_USER": DB_USER,
    "DB_PASSWORD": DB_PASSWORD,
}

missing = [key for key, value in required.items() if not value]
if missing:
    raise EnvironmentError(f"Missing required environment variables: {missing}")


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
        "EMAIL_PASSWORD": EMAIL_PASSWORD,
        "EMAIL_RECIPIENT": EMAIL_RECIPIENT,
        "SMTP_HOST": SMTP_HOST,
    }
    missing_email = [key for key, value in required_email.items() if not value]
    if missing_email:
        raise EnvironmentError(
            f"Missing email environment variables: {missing_email}"
        )