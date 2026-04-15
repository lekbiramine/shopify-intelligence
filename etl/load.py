import time
from db.queries import (
    upsert_product,
    upsert_variant,
    upsert_customer,
    upsert_order,
    upsert_order_item,
    upsert_inventory,
)
from db.connection import get_cursor
from config import constants
from config.logging_config import get_logger

logger = get_logger(__name__)

LOG_EVERY_N = 100


def _upsert_with_retry(upsert_fn, record: dict, label: str) -> bool:
    """
    Attempts to upsert a record with retry logic.
    Returns True on success, False on total failure.
    """
    for attempt in range(1, constants.PIPELINE_RETRY_ATTEMPTS + 1):
        try:
            upsert_fn(record)
            return True
        except Exception as e:
            logger.warning(
                f"{label} upsert failed (attempt {attempt}/{constants.PIPELINE_RETRY_ATTEMPTS}): {e}"
            )
            if attempt < constants.PIPELINE_RETRY_ATTEMPTS:
                time.sleep(constants.PIPELINE_RETRY_DELAY)

    logger.error(f"{label} upsert permanently failed after {constants.PIPELINE_RETRY_ATTEMPTS} attempts.")
    return False


def _load_records(records: list[dict], upsert_fn, label: str) -> None:
    """
    Generic loader — iterates records, retries on failure,
    wraps every BATCH_SIZE records in a transaction,
    and logs progress every LOG_EVERY_N records.
    """
    if not records:
        logger.warning(f"No {label} records to load.")
        return

    success = 0
    failed = 0
    batch_size = 100

    for i in range(0, len(records), batch_size):
        batch = records[i: i + batch_size]
        try:
            with get_cursor(commit=True) as cursor:
                for j, record in enumerate(batch, start=i + 1):
                    ok = _upsert_with_retry(upsert_fn, record, label)
                    if ok:
                        success += 1
                    else:
                        failed += 1

                    if j % LOG_EVERY_N == 0:
                        logger.info(f"{label}: processed {j}/{len(records)} records...")

        except Exception as e:
            logger.error(f"{label} batch {i // batch_size + 1} transaction failed: {e}")
            failed += len(batch)

    logger.info(f"{label} load complete — success: {success}, failed: {failed}.")


def load_products(products: list[dict], variants: list[dict]) -> None:
    logger.info(f"Loading {len(products)} products into database...")
    _load_records(products, upsert_product, "Product")

    logger.info(f"Loading {len(variants)} variants into database...")
    _load_records(variants, upsert_variant, "Variant")


def load_customers(customers: list[dict]) -> None:
    logger.info(f"Loading {len(customers)} customers into database...")
    _load_records(customers, upsert_customer, "Customer")


def load_orders(orders: list[dict], order_items: list[dict]) -> None:
    logger.info(f"Loading {len(orders)} orders into database...")
    _load_records(orders, upsert_order, "Order")

    logger.info(f"Loading {len(order_items)} order items into database...")
    _load_records(order_items, upsert_order_item, "OrderItem")


def load_inventory(inventory: list[dict]) -> None:
    logger.info(f"Loading {len(inventory)} inventory records into database...")
    _load_records(inventory, upsert_inventory, "Inventory")


def attach_store_id(records: list[dict], store_id: int) -> list[dict]:
    if not records:
        return []
    for r in records:
        r["store_id"] = store_id
    return records