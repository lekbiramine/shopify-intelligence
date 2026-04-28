from db.connection import get_cursor
from config.logging_config import get_logger

logger = get_logger(__name__)


def get_duplicate_orders(store_id: int) -> list[dict]:
    """
    Returns customers who placed more than one order on the same day
    with the same total price — likely duplicate charges.
    """
    sql = """
        SELECT
            customer_id,
            DATE(created_at) AS order_date,
            total_price,
            COUNT(*) AS order_count
        FROM orders
        WHERE store_id = %(store_id)s
        GROUP BY customer_id, DATE(created_at), total_price
        HAVING COUNT(*) > 1
        ORDER BY order_count DESC;
    """
    with get_cursor() as cursor:
        cursor.execute(sql, {"store_id": store_id})
        results = cursor.fetchall()

    logger.info(f"Found {len(results)} potential duplicate orders.")
    return [dict(r) for r in results]


def get_orders_with_zero_value(store_id: int) -> list[dict]:
    """
    Returns paid orders with zero or negative total price — likely data issues.
    """
    sql = """
        SELECT
            o.id AS order_id,
            o.customer_id,
            o.email,
            o.total_price,
            o.financial_status,
            o.created_at
        FROM orders o
        WHERE o.store_id = %(store_id)s
        AND o.financial_status = 'paid'
        AND o.total_price <= 0
        ORDER BY o.created_at DESC;
    """
    with get_cursor() as cursor:
        cursor.execute(sql, {"store_id": store_id})
        results = cursor.fetchall()

    logger.info(f"Found {len(results)} zero-value paid orders.")
    return [dict(r) for r in results]


def get_abnormal_discount_orders(store_id: int) -> list[dict]:
    """
    Returns orders where discounts exceed 80% of subtotal — unusually high.
    """
    sql = """
        SELECT
            o.id AS order_id,
            o.customer_id,
            o.email,
            o.subtotal_price,
            o.total_discounts,
            ROUND(o.total_discounts / NULLIF(o.subtotal_price, 0) * 100, 2) AS discount_pct,
            o.created_at
        FROM orders o
        WHERE o.store_id = %(store_id)s
        AND o.subtotal_price > 0
        AND (o.total_discounts / NULLIF(o.subtotal_price, 0)) >= 0.8
        ORDER BY discount_pct DESC;
    """
    with get_cursor() as cursor:
        cursor.execute(sql, {"store_id": store_id})
        results = cursor.fetchall()

    logger.info(f"Found {len(results)} orders with abnormal discounts.")
    return [dict(r) for r in results]


def get_products_with_no_sales(store_id: int) -> list[dict]:
    """
    Returns active products that have never appeared in any order.

    Includes an approximate on-hand inventory value using variant price * available inventory.
    This is not COGS; it's a liquidation/cash-tied approximation for decision-making.
    """
    sql = """
        SELECT
            p.id AS product_id,
            p.title AS product_title,
            p.vendor,
            p.product_type,
            p.created_at,
            COALESCE(SUM(i.available), 0) AS total_available,
            COALESCE(AVG(NULLIF(v.price, 0)), 0) AS avg_variant_price,
            COALESCE(SUM(i.available) * AVG(NULLIF(v.price, 0)), 0) AS est_on_hand_value
        FROM products p
        LEFT JOIN order_items oi ON oi.store_id = p.store_id AND oi.product_id = p.id
        LEFT JOIN variants v ON v.store_id = p.store_id AND v.product_id = p.id
        LEFT JOIN inventory i ON i.store_id = v.store_id AND i.variant_id = v.id
        WHERE p.store_id = %(store_id)s
        AND p.status = 'active'
        AND oi.id IS NULL
        GROUP BY p.id, p.title, p.vendor, p.product_type, p.created_at
        HAVING COALESCE(SUM(i.available), 0) > 0
        ORDER BY est_on_hand_value DESC, p.created_at DESC;
    """
    with get_cursor() as cursor:
        cursor.execute(sql, {"store_id": store_id})
        results = cursor.fetchall()

    logger.info(f"Found {len(results)} active products with no sales.")
    return [dict(r) for r in results]