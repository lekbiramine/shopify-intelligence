from pathlib import Path
import argparse
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config.logging_config import get_logger, setup_logging
from db.queries import upsert_store_connection, update_store_contact_email
from utils.client_env import env_value, load_client_env
from utils.shopify_auth import (
    fetch_access_scopes,
    normalize_shop_domain,
    validate_access_token,
    validate_read_only_scopes,
)

logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manual onboarding for managed clients (domain + token).",
    )
    parser.add_argument("--env-file", default="", help="Optional path to per-client .env file")
    parser.add_argument("--shop-domain", default="", help="Shop domain, e.g. my-store.myshopify.com")
    parser.add_argument("--access-token", default="", help="Shopify Admin API token")
    parser.add_argument("--contact-email", default="", help="Recipient email for reports")
    return parser.parse_args()


def main() -> None:
    setup_logging()
    args = parse_args()
    loaded_env = load_client_env(args.env_file)

    shop_domain_raw = (args.shop_domain or "").strip() or env_value("CLIENT_SHOP_DOMAIN", "SHOPIFY_STORE_URL")
    access_token = (args.access_token or "").strip() or env_value("CLIENT_ACCESS_TOKEN", "SHOPIFY_ACCESS_TOKEN")
    contact_email = (args.contact_email or "").strip() or env_value("CLIENT_CONTACT_EMAIL", "EMAIL_RECIPIENT")

    if not shop_domain_raw:
        raise ValueError("shop-domain is required (or set CLIENT_SHOP_DOMAIN in env file)")
    shop_domain = normalize_shop_domain(shop_domain_raw)
    if not access_token:
        raise ValueError("access-token is required (or set CLIENT_ACCESS_TOKEN in env file)")
    if not contact_email:
        raise ValueError("contact-email is required (or set CLIENT_CONTACT_EMAIL in env file)")

    ok, detail = validate_access_token(shop_domain, access_token)
    if not ok:
        raise RuntimeError(detail)

    scopes = fetch_access_scopes(shop_domain, access_token)
    scopes_ok, scopes_detail = validate_read_only_scopes(scopes)
    if not scopes_ok:
        raise RuntimeError(scopes_detail)

    upsert_store_connection(
        shop_domain=shop_domain,
        access_token=access_token,
        scope=",".join(scopes),
        contact_email=contact_email,
    )
    update_store_contact_email(shop_domain, contact_email)
    logger.info("Manual onboarding completed for %s", shop_domain)
    if loaded_env:
        logger.info("Loaded onboarding values from %s", loaded_env)


if __name__ == "__main__":
    main()
