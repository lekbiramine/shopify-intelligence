from datetime import datetime, timedelta, timezone
from pathlib import Path

from config.logging_config import get_logger
from config import settings
from db.queries import create_report_record, get_store_contact_email_by_id, update_store_auth_tokens
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
from reporting.email_sender import send_store_report_email
from reporting.pdf_report_v2 import create_report_pdf
from tasks.engine import (
    auto_verify_tasks_from_summary,
    build_report_task_sections,
    collect_due_reminders,
    evaluate_completed_task_impacts,
    sync_tasks_from_summary,
)
from utils.decorators import log_execution
from utils.shopify_auth import (
    fetch_access_scopes,
    migrate_non_expiring_offline_token,
    refresh_access_token,
    validate_access_token,
    validate_read_only_scopes,
)

logger = get_logger(__name__)


def _ensure_store_access_token(
    *,
    shop_domain: str,
    access_token: str,
    refresh_token: str | None = None,
    access_token_expires_at=None,
) -> str:
    """
    Returns a usable access token, refreshing it when needed.
    """
    token = (access_token or "").strip()
    if not token:
        raise RuntimeError(f"Missing access token for {shop_domain}")

    # Refresh proactively if token is near expiry.
    should_refresh = False
    if access_token_expires_at:
        try:
            if datetime.now(timezone.utc) + timedelta(minutes=2) >= access_token_expires_at:
                should_refresh = True
        except Exception:
            logger.warning("Invalid access_token_expires_at for %s; continuing with current token", shop_domain)

    if should_refresh:
        if not (refresh_token or "").strip():
            raise RuntimeError(f"Access token for {shop_domain} is expiring and no refresh token is stored.")
        refreshed = refresh_access_token(shop_domain, refresh_token)
        token = refreshed["access_token"]
        update_store_auth_tokens(
            shop_domain,
            access_token=token,
            refresh_token=refreshed.get("refresh_token"),
            access_token_expires_at=refreshed.get("access_token_expires_at"),
        )
        logger.info("Refreshed access token for %s", shop_domain)
        return token

    token_ok, _ = validate_access_token(shop_domain, token)
    if token_ok:
        return token

    # If current token is invalid and we have a refresh token, rotate and retry.
    if (refresh_token or "").strip():
        refreshed = refresh_access_token(shop_domain, refresh_token)
        token = refreshed["access_token"]
        update_store_auth_tokens(
            shop_domain,
            access_token=token,
            refresh_token=refreshed.get("refresh_token"),
            access_token_expires_at=refreshed.get("access_token_expires_at"),
        )
        logger.info("Rotated invalid access token for %s", shop_domain)
        return token

    # Last attempt: one-time Shopify migration from non-expiring -> expiring offline token.
    migrated = migrate_non_expiring_offline_token(shop_domain, token)
    token = migrated["access_token"]
    update_store_auth_tokens(
        shop_domain,
        access_token=token,
        refresh_token=migrated.get("refresh_token"),
        access_token_expires_at=migrated.get("access_token_expires_at"),
    )
    logger.info("Migrated non-expiring offline token for %s", shop_domain)
    return token


@log_execution
def run_etl_for_store(
    *,
    store_id: int,
    shop_domain: str,
    access_token: str,
    refresh_token: str | None = None,
    access_token_expires_at=None,
) -> None:
    logger.info("Starting ETL pipeline...")
    access_token = _ensure_store_access_token(
        shop_domain=shop_domain,
        access_token=access_token,
        refresh_token=refresh_token,
        access_token_expires_at=access_token_expires_at,
    )
    token_ok, token_detail = validate_access_token(shop_domain, access_token)
    if not token_ok:
        raise RuntimeError(f"Token validation failed for {shop_domain}: {token_detail}")
    scopes = fetch_access_scopes(shop_domain, access_token)
    logger.info("Granted scopes for %s: %s", shop_domain, ",".join(scopes))
    scopes_ok, scopes_detail = validate_read_only_scopes(scopes)
    if not scopes_ok:
        raise RuntimeError(f"Scope validation failed for {shop_domain}: {scopes_detail}")
    logger.info(
        "Scope check passed for %s (read_customers=%s, read_orders=%s)",
        shop_domain,
        "read_customers" in set(scopes),
        "read_orders" in set(scopes),
    )

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


def _assert_store_report_delivery_scope(*, store_id: int, report_path: str, recipient_email: str) -> None:
    expected = get_store_contact_email_by_id(store_id)
    if not expected:
        raise RuntimeError(f"No contact_email configured for store_id={store_id}")
    if recipient_email.strip().lower() != expected.strip().lower():
        raise RuntimeError(
            f"Recipient email mismatch for store_id={store_id}: expected {expected}, got {recipient_email}"
        )
    normalized = str(Path(report_path)).replace("\\", "/")
    if f"/reports/{store_id}/" not in f"/{normalized}":
        raise RuntimeError(f"Report path is not store-scoped: {report_path}")


@log_execution
def run_reporting_for_store(*, store_id: int) -> tuple[str, str]:
    logger.info("Starting reporting pipeline...", extra={"store_id": store_id})

    summary = build_summary(store_id)
    sync_tasks_from_summary(store_id, summary)
    auto_verify_tasks_from_summary(store_id, summary)
    evaluate_completed_task_impacts(store_id, summary)
    reminders = collect_due_reminders(store_id)
    task_sections = build_report_task_sections(store_id, summary)
    pdf_path = create_report_pdf(summary, output_dir=f"reports/{store_id}", task_sections=task_sections, store_id=store_id)
    recipient_email = get_store_contact_email_by_id(store_id) or ""
    _assert_store_report_delivery_scope(store_id=store_id, report_path=pdf_path, recipient_email=recipient_email)
    subject = get_email_subject()
    reminder_lines = []
    for task in reminders[:5]:
        reminder_lines.append(f"- [{task.get('status')}] {task.get('title')} (impact ${float(task.get('expected_impact') or 0):,.2f})")
    reminder_block = ""
    if reminder_lines:
        reminder_block = "\n\nTask reminders:\n" + "\n".join(reminder_lines)
    email_body = (
        "Your daily Store Intelligence report is attached as a PDF.\n\n"
        f"Attachment: {pdf_path}"
        f"{reminder_block}"
    )
    recipient = send_store_report_email(store_id=store_id, subject=subject, body=email_body, attachment_path=pdf_path)
    create_report_record(store_id=store_id, report_path=pdf_path, recipient_email=recipient)

    logger.info("Reporting pipeline completed.", extra={"store_id": store_id, "report_path": pdf_path, "recipient": recipient})
    return pdf_path, recipient


@log_execution
def run_etl() -> None:
    """
    Backwards compatible single-store ETL task driven by env vars.
    """
    settings.validate_shopify_pipeline_env()
    from db.queries import get_store_by_domain

    store = get_store_by_domain(settings.SHOPIFY_STORE_URL)
    if not store:
        raise RuntimeError("No store row found for SHOPIFY_STORE_URL; connect the store via onboarding first.")

    run_etl_for_store(
        store_id=store["id"],
        shop_domain=settings.SHOPIFY_STORE_URL,
        access_token=store.get("access_token") or settings.SHOPIFY_ACCESS_TOKEN,
        refresh_token=store.get("refresh_token"),
        access_token_expires_at=store.get("access_token_expires_at"),
    )


@log_execution
def run_reporting() -> None:
    """
    Backwards compatible single-store reporting task driven by env vars.
    """
    settings.validate_email_env()
    from db.queries import get_store_by_domain

    store = get_store_by_domain(settings.SHOPIFY_STORE_URL)
    if not store:
        raise RuntimeError("No store row found for SHOPIFY_STORE_URL; connect the store via onboarding first.")

    run_reporting_for_store(store_id=store["id"])


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

    run_etl_for_store(
        store_id=store["id"],
        shop_domain=settings.SHOPIFY_STORE_URL,
        access_token=store.get("access_token") or settings.SHOPIFY_ACCESS_TOKEN,
        refresh_token=store.get("refresh_token"),
        access_token_expires_at=store.get("access_token_expires_at"),
    )
    run_reporting_for_store(store_id=store["id"])

    logger.info("=" * 50)
    logger.info("PIPELINE COMPLETED SUCCESSFULLY")
    logger.info("=" * 50)


if __name__ == "__main__":
    from config.logging_config import setup_logging

    setup_logging()
    run_pipeline()