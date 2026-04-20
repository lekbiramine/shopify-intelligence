from pathlib import Path
import argparse
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config.logging_config import get_logger, setup_logging
from db.queries import complete_job_run, create_job_run, get_store_by_domain
from scheduler.run_pipeline import run_etl_for_store, run_reporting_for_store
from utils.client_env import env_value, load_client_env
from utils.shopify_auth import normalize_shop_domain

logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run ETL+reporting for one onboarded store.",
    )
    parser.add_argument("--env-file", default="", help="Optional path to per-client .env file")
    parser.add_argument("--shop-domain", default="", help="Store domain, e.g. my-store.myshopify.com")
    parser.add_argument("--recipient-email", default="", help="Optional override recipient email")
    return parser.parse_args()


def main() -> None:
    setup_logging()
    args = parse_args()
    loaded_env = load_client_env(args.env_file)
    shop_domain_raw = (args.shop_domain or "").strip() or env_value("CLIENT_SHOP_DOMAIN", "SHOPIFY_STORE_URL")
    if not shop_domain_raw:
        raise ValueError("shop-domain is required (or set CLIENT_SHOP_DOMAIN in env file)")
    shop_domain = normalize_shop_domain(shop_domain_raw)
    store = get_store_by_domain(shop_domain) or {}

    store_id = store.get("id")
    access_token = (store.get("access_token") or "").strip()
    refresh_token = (store.get("refresh_token") or "").strip() or None
    access_token_expires_at = store.get("access_token_expires_at")
    recipient = (args.recipient_email or store.get("contact_email") or env_value("CLIENT_CONTACT_EMAIL", "EMAIL_RECIPIENT") or "").strip()
    if not store_id or not access_token:
        raise RuntimeError(f"Store not onboarded with credentials: {shop_domain}")
    if not recipient:
        raise RuntimeError(f"Missing recipient email for store: {shop_domain}")

    logger.info("Running managed job for %s", shop_domain)
    job_run_id = create_job_run(store_id=store_id, shop_domain=shop_domain)
    email_sent = False
    try:
        run_etl_for_store(
            store_id=store_id,
            shop_domain=shop_domain,
            access_token=access_token,
            refresh_token=refresh_token,
            access_token_expires_at=access_token_expires_at,
        )
        run_reporting_for_store(store_id=store_id, recipient_email=recipient)
        email_sent = True
        complete_job_run(job_run_id, status="success", email_sent=email_sent, error_message=None)
        logger.info("Managed job completed for %s", shop_domain)
    except Exception as exc:
        complete_job_run(
            job_run_id,
            status="failed",
            email_sent=email_sent,
            error_message=str(exc)[:4000],
        )
        logger.exception("Managed job failed for %s", shop_domain)
        raise

    if loaded_env:
        logger.info("Loaded job values from %s", loaded_env)


if __name__ == "__main__":
    main()
