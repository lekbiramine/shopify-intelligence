from config.logging_config import get_logger
from config import settings
from etl.extract import (
    fetch_products,
    fetch_customers,
    fetch_orders,
    fetch_inventory_levels,
)
from etl.transform import (
    transform_products,
    transform_customers,
    transform_orders,
    transform_inventory,
)
from etl.load import (
    attach_store_id,
    load_products,
    load_customers,
    load_orders,
    load_inventory,
)
from analytics.summary import build_summary
from reporting.templates import get_email_subject
from reporting.email_sender import send_email
from reporting.pdf_report import create_report_pdf
from utils.decorators import log_execution

logger = get_logger(__name__)


@log_execution
def run_etl_for_store(*, store_id: int, shop_domain: str, access_token: str) -> None:
    logger.info("Starting ETL pipeline...")

    # Extract
    raw_products = fetch_products(shop_domain=shop_domain, access_token=access_token)
    raw_customers = fetch_customers(shop_domain=shop_domain, access_token=access_token)
    raw_orders = fetch_orders(shop_domain=shop_domain, access_token=access_token)

    # Transform
    products, variants = transform_products(raw_products)
    customers = transform_customers(raw_customers)
    orders, order_items = transform_orders(raw_orders)

    # Extract inventory item IDs from variants
    inventory_item_ids = [
        v["id"] for v in variants if v.get("id")
    ]
    raw_inventory = fetch_inventory_levels(inventory_item_ids, shop_domain=shop_domain, access_token=access_token)
    inventory = transform_inventory(raw_inventory)

    # Load
    load_products(attach_store_id(products, store_id), attach_store_id(variants, store_id))
    load_customers(attach_store_id(customers, store_id))
    load_orders(attach_store_id(orders, store_id), attach_store_id(order_items, store_id))
    load_inventory(attach_store_id(inventory, store_id))

    logger.info("ETL pipeline completed.")


@log_execution
def run_reporting_for_store(*, store_id: int, recipient_email: str) -> None:
    logger.info("Starting reporting pipeline...")

    summary = build_summary(store_id)
    pdf_path = create_report_pdf(summary)
    subject = get_email_subject()
    email_body = (
        "Your daily Store Intelligence report is attached as a PDF.\n\n"
        f"Attachment: {pdf_path}"
    )
    send_email(subject, email_body, attachment_path=pdf_path, recipient=recipient_email)

    logger.info("Reporting pipeline completed.")


@log_execution
def run_pipeline() -> None:
    # Backwards compatible: single-store run via env vars
    logger.info("=" * 50)
    logger.info("PIPELINE STARTED")
    logger.info("=" * 50)

    settings.validate_shopify_pipeline_env()
    settings.validate_email_env()
    # If you're using the legacy single-store mode, you must have already created one store row.
    from db.queries import get_store_by_domain

    store = get_store_by_domain(settings.SHOPIFY_STORE_URL)
    if not store:
        raise RuntimeError("No store row found for SHOPIFY_STORE_URL; connect the store via onboarding first.")

    run_etl_for_store(store_id=store["id"], shop_domain=settings.SHOPIFY_STORE_URL, access_token=settings.SHOPIFY_ACCESS_TOKEN)
    recipient = (store.get("contact_email") or settings.EMAIL_RECIPIENT or "").strip()
    if not recipient:
        raise RuntimeError("No recipient email found for store.")
    run_reporting_for_store(store_id=store["id"], recipient_email=recipient)

    logger.info("=" * 50)
    logger.info("PIPELINE COMPLETED SUCCESSFULLY")
    logger.info("=" * 50)


if __name__ == "__main__":
    from config.logging_config import setup_logging

    setup_logging()
    run_pipeline()