import logging
import os
import sys
from pathlib import Path

import modal

sys.path.insert(0, "/root")

ENV_SECRET_KEYS = [
    "DB_HOST",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
    "DB_PORT",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USERNAME",
    "EMAIL_PASSWORD",
    "EMAIL_FROM",
    "SHOPIFY_API_KEY",
    "SHOPIFY_API_SECRET",
    "SECRET_KEY",
    "FRONTEND_URL",
]

PROJECT_ROOT = Path(__file__).resolve().parents[1]

image = (
    modal.Image.debian_slim()
    .pip_install_from_requirements("requirements.txt")
    .workdir("/root")
    .add_local_dir(str(PROJECT_ROOT), remote_path="/root")
)
app = modal.App("perspicor", image=image)
pipeline_secret = modal.Secret.from_name("perspicor-env", required_keys=ENV_SECRET_KEYS)


@app.function(
    secrets=[pipeline_secret],
    timeout=60 * 60 * 24,
)
def run_store_pipeline(shop_domain: str) -> None:
    os.chdir("/root")
    if "/root" not in sys.path:
        sys.path.insert(0, "/root")

    from config.logging_config import get_logger, setup_logging
    from db.queries import get_store_by_domain
    from scheduler.run_pipeline import run_etl_for_store, run_reporting_for_store

    setup_logging()
    logger = get_logger(__name__)
    normalized_domain = str(shop_domain or "").strip().lower()
    os.environ.setdefault("PERSPICOR_LOGO_URL", "https://perspicor.com/perspicor-mark.png")
    logger.info("Modal pipeline started for %s", normalized_domain)

    try:
        store = get_store_by_domain(normalized_domain)
        if not store:
            raise RuntimeError(f"No connected store found for {normalized_domain}")

        store_id = int(store["id"])
        run_etl_for_store(
            store_id=store_id,
            shop_domain=normalized_domain,
            access_token=str(store.get("access_token") or "").strip(),
            refresh_token=(str(store.get("refresh_token") or "").strip() or None),
            access_token_expires_at=store.get("access_token_expires_at"),
        )
        run_reporting_for_store(store_id=store_id)
        logger.info("Modal pipeline completed for %s (store_id=%s)", normalized_domain, store_id)
    except Exception:
        logger.exception("Modal pipeline failed for %s", normalized_domain)
        raise


def spawn_store_pipeline_job(shop_domain: str):
    from config import settings

    logger = logging.getLogger(__name__)
    normalized_domain = str(shop_domain or "").strip().lower()
    if not normalized_domain:
        raise ValueError("shop_domain is required")

    # Ensure Modal client auth is available in process env for local/Vercel callers.
    settings.validate_modal_env()
    os.environ["MODAL_TOKEN_ID"] = settings.MODAL_TOKEN_ID
    os.environ["MODAL_TOKEN_SECRET"] = settings.MODAL_TOKEN_SECRET

    job = modal.Function.from_name("perspicor", "run_store_pipeline").spawn(normalized_domain)
    logger.info("Spawned Modal pipeline job for %s", normalized_domain)
    return job


@app.local_entrypoint()
def main(shop_domain: str) -> None:
    run_store_pipeline.remote(shop_domain)
