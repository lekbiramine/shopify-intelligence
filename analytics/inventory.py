from db.connection import get_cursor
from config import constants
from config.logging_config import get_logger

logger = get_logger(__name__)


def _get_stock_products(min_qty: int, max_qty: int) -> list[dict]:
    """
    Variants whose summed available inventory falls in [min_qty, max_qty] (inclusive).
    Bands are mutually exclusive: out of stock 0, critical 1–5, low 6–10 by default.
    """
    sql = """
        SELECT
            p.id AS product_id,
            p.title AS product_title,
            p.vendor,
            v.id AS variant_id,
            v.title AS variant_title,
            v.sku,
            v.price,
            COALESCE(SUM(i.available), 0) AS total_available
        FROM products p
        JOIN variants v ON v.product_id = p.id
        LEFT JOIN inventory i ON i.variant_id = v.id
        WHERE p.status = 'active'
        GROUP BY p.id, p.title, p.vendor, v.id, v.title, v.sku, v.price
        HAVING COALESCE(SUM(i.available), 0) >= %(min_qty)s
        AND COALESCE(SUM(i.available), 0) <= %(max_qty)s
        ORDER BY total_available ASC;
    """
    with get_cursor() as cursor:
        cursor.execute(sql, {"min_qty": min_qty, "max_qty": max_qty})
        results = cursor.fetchall()

    return [dict(r) for r in results]


def get_low_stock_products() -> list[dict]:
    results = _get_stock_products(
        constants.CRITICAL_STOCK_THRESHOLD + 1,
        constants.LOW_STOCK_THRESHOLD,
    )
    logger.info(f"Found {len(results)} low stock variants.")
    return results


def get_critical_stock_products() -> list[dict]:
    results = _get_stock_products(1, constants.CRITICAL_STOCK_THRESHOLD)
    logger.info(f"Found {len(results)} critical stock variants.")
    return results


def get_out_of_stock_products() -> list[dict]:
    results = _get_stock_products(0, 0)
    logger.info(f"Found {len(results)} out of stock variants.")
    return results