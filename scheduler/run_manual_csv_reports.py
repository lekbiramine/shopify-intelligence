import argparse
import csv
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config.logging_config import get_logger, setup_logging
from db.queries import get_store_by_domain, upsert_store_contact_email
from etl.load import (
    attach_store_id,
    load_customers,
    load_inventory,
    load_orders,
    load_products,
)
from scheduler.run_pipeline import run_reporting_for_store

logger = get_logger(__name__)


def _to_int(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _norm(key: str) -> str:
    return (key or "").strip().lower()


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        logger.warning("CSV not found: %s", path)
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader)


def _row_get(row: dict[str, Any], *keys: str, default: Any = None) -> Any:
    normalized = {_norm(k): v for k, v in row.items()}
    for key in keys:
        value = normalized.get(_norm(key))
        if value is not None and value != "":
            return value
    return default


def _parse_products(data_dir: Path) -> tuple[list[dict], list[dict]]:
    products_rows = _read_csv_rows(data_dir / "products.csv")
    variants_rows = _read_csv_rows(data_dir / "variants.csv")

    products: list[dict] = []
    for row in products_rows:
        pid = _to_int(_row_get(row, "id", "product_id"), default=0)
        if not pid:
            continue
        products.append(
            {
                "id": pid,
                "title": _row_get(row, "title", default="Unknown product"),
                "vendor": _row_get(row, "vendor"),
                "product_type": _row_get(row, "product_type"),
                "status": _row_get(row, "status"),
                "created_at": _row_get(row, "created_at"),
                "updated_at": _row_get(row, "updated_at"),
            }
        )

    variants: list[dict] = []
    for row in variants_rows:
        vid = _to_int(_row_get(row, "id", "variant_id"), default=0)
        pid = _to_int(_row_get(row, "product_id"), default=0)
        if not vid or not pid:
            continue
        variants.append(
            {
                "id": vid,
                "product_id": pid,
                "title": _row_get(row, "title"),
                "sku": _row_get(row, "sku"),
                "price": _to_float(_row_get(row, "price"), default=0.0),
                "inventory_quantity": _to_int(_row_get(row, "inventory_quantity"), default=0),
                "updated_at": _row_get(row, "updated_at"),
            }
        )
    return products, variants


def _parse_customers(data_dir: Path) -> list[dict]:
    rows = _read_csv_rows(data_dir / "customers.csv")
    customers: list[dict] = []
    for row in rows:
        cid = _to_int(_row_get(row, "id", "customer_id"), default=0)
        if not cid:
            continue
        customers.append(
            {
                "id": cid,
                "email": _row_get(row, "email"),
                "first_name": _row_get(row, "first_name"),
                "last_name": _row_get(row, "last_name"),
                "orders_count": _to_int(_row_get(row, "orders_count"), default=0),
                "total_spent": _to_float(_row_get(row, "total_spent"), default=0.0),
                "created_at": _row_get(row, "created_at"),
                "updated_at": _row_get(row, "updated_at"),
            }
        )
    return customers


def _parse_orders(data_dir: Path) -> tuple[list[dict], list[dict]]:
    orders_rows = _read_csv_rows(data_dir / "orders.csv")
    items_rows = _read_csv_rows(data_dir / "order_items.csv")

    orders: list[dict] = []
    for row in orders_rows:
        oid = _to_int(_row_get(row, "id", "order_id"), default=0)
        if not oid:
            continue
        orders.append(
            {
                "id": oid,
                "customer_id": _to_int(_row_get(row, "customer_id"), default=0) or None,
                "email": _row_get(row, "email"),
                "total_price": _to_float(_row_get(row, "total_price"), default=0.0),
                "subtotal_price": _to_float(_row_get(row, "subtotal_price"), default=0.0),
                "total_discounts": _to_float(_row_get(row, "total_discounts"), default=0.0),
                "financial_status": _row_get(row, "financial_status"),
                "fulfillment_status": _row_get(row, "fulfillment_status"),
                "created_at": _row_get(row, "created_at"),
                "updated_at": _row_get(row, "updated_at"),
            }
        )

    order_items: list[dict] = []
    for row in items_rows:
        iid = _to_int(_row_get(row, "id", "order_item_id", "line_item_id"), default=0)
        oid = _to_int(_row_get(row, "order_id"), default=0)
        if not iid or not oid:
            continue
        order_items.append(
            {
                "id": iid,
                "order_id": oid,
                "product_id": _to_int(_row_get(row, "product_id"), default=0) or None,
                "variant_id": _to_int(_row_get(row, "variant_id"), default=0) or None,
                "title": _row_get(row, "title"),
                "quantity": _to_int(_row_get(row, "quantity"), default=0),
                "price": _to_float(_row_get(row, "price"), default=0.0),
                "total_discount": _to_float(_row_get(row, "total_discount"), default=0.0),
                "vendor": _row_get(row, "vendor"),
            }
        )
    return orders, order_items


def _parse_inventory(data_dir: Path) -> list[dict]:
    rows = _read_csv_rows(data_dir / "inventory.csv")
    inventory: list[dict] = []
    for row in rows:
        variant_id = _to_int(_row_get(row, "variant_id"), default=0)
        location_id = _to_int(_row_get(row, "location_id"), default=0)
        if not variant_id or not location_id:
            continue
        inventory.append(
            {
                "variant_id": variant_id,
                "inventory_item_id": _to_int(_row_get(row, "inventory_item_id"), default=0) or None,
                "location_id": location_id,
                "available": _to_int(_row_get(row, "available"), default=0),
            }
        )
    return inventory


def _ensure_store(shop_domain: str, recipient_email: str) -> int:
    upsert_store_contact_email(shop_domain, recipient_email)
    store = get_store_by_domain(shop_domain)
    if not store:
        raise RuntimeError(f"Failed to initialize store record for {shop_domain}")
    return int(store["id"])


def _run_manual_ingest(store_id: int, data_dir: Path) -> None:
    products, variants = _parse_products(data_dir)
    customers = _parse_customers(data_dir)
    orders, order_items = _parse_orders(data_dir)
    inventory = _parse_inventory(data_dir)

    load_products(attach_store_id(products, store_id), attach_store_id(variants, store_id))
    load_customers(attach_store_id(customers, store_id))
    load_orders(attach_store_id(orders, store_id), attach_store_id(order_items, store_id))
    load_inventory(attach_store_id(inventory, store_id))

    logger.info(
        "Manual CSV ingest completed: products=%s variants=%s customers=%s orders=%s items=%s inventory=%s",
        len(products),
        len(variants),
        len(customers),
        len(orders),
        len(order_items),
        len(inventory),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run manual service workflow from exported CSV files.",
    )
    parser.add_argument(
        "--shop-domain",
        required=True,
        help="Logical store key for this client (example: client-a.myshopify.com).",
    )
    parser.add_argument(
        "--recipient-email",
        required=True,
        help="Where the report email will be sent.",
    )
    parser.add_argument(
        "--data-dir",
        default="data/manual_export",
        help="Directory containing products.csv, variants.csv, customers.csv, orders.csv, order_items.csv, inventory.csv.",
    )
    return parser.parse_args()


def main() -> None:
    setup_logging()
    args = parse_args()
    data_dir = Path(args.data_dir).resolve()
    if not data_dir.exists():
        raise FileNotFoundError(f"Data directory does not exist: {data_dir}")

    shop_domain = (args.shop_domain or "").strip().lower()
    recipient_email = (args.recipient_email or "").strip()
    if not shop_domain:
        raise ValueError("shop-domain is required")
    if not recipient_email:
        raise ValueError("recipient-email is required")

    logger.info("Starting manual CSV workflow for %s from %s", shop_domain, data_dir)
    store_id = _ensure_store(shop_domain, recipient_email)
    _run_manual_ingest(store_id, data_dir)
    run_reporting_for_store(store_id=store_id, recipient_email=recipient_email)
    logger.info("Manual CSV workflow completed successfully for %s", shop_domain)


if __name__ == "__main__":
    main()
