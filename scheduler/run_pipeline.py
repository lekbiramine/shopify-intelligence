from config.logging_config import get_logger
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
    load_products,
    load_customers,
    load_orders,
    load_inventory,
)
from analytics.summary import build_summary
from reporting.formatter import format_full_report
from reporting.templates import get_email_subject, wrap_email_body
from reporting.email_sender import send_email
from utils.decorators import log_execution

logger = get_logger(__name__)


@log_execution
def run_etl() -> None:
    logger.info("Starting ETL pipeline...")

    # Extract
    raw_products = fetch_products()
    raw_customers = fetch_customers()
    raw_orders = fetch_orders()

    # Transform
    products, variants = transform_products(raw_products)
    customers = transform_customers(raw_customers)
    orders, order_items = transform_orders(raw_orders)

    # Extract inventory item IDs from variants
    inventory_item_ids = [
        v["id"] for v in variants if v.get("id")
    ]
    raw_inventory = fetch_inventory_levels(inventory_item_ids)
    inventory = transform_inventory(raw_inventory)

    # Load
    load_products(products, variants)
    load_customers(customers)
    load_orders(orders, order_items)
    load_inventory(inventory)

    logger.info("ETL pipeline completed.")


@log_execution
def run_reporting() -> None:
    logger.info("Starting reporting pipeline...")

    summary = build_summary()
    report_body = format_full_report(summary)
    email_body = wrap_email_body(report_body)
    subject = get_email_subject()
    send_email(subject, email_body)

    logger.info("Reporting pipeline completed.")


@log_execution
def run_pipeline() -> None:
    logger.info("=" * 50)
    logger.info("PIPELINE STARTED")
    logger.info("=" * 50)

    run_etl()
    run_reporting()

    logger.info("=" * 50)
    logger.info("PIPELINE COMPLETED SUCCESSFULLY")
    logger.info("=" * 50)


if __name__ == "__main__":
    from config.logging_config import setup_logging

    setup_logging()
    run_pipeline()