from db.connection import get_cursor
from config import constants
from config.logging_config import get_logger

logger = get_logger(__name__)


def get_high_return_rate_products(store_id: int) -> list[dict]:
    """
    Returns products where return rate exceeds HIGH_RETURN_RATE_THRESHOLD.
    Uses refunded/cancelled orders as a proxy for returns.
    """
    sql = """
        SELECT
            oi.product_id,
            p.title AS product_title,
            p.vendor,
            COUNT(oi.id) AS total_sold,
            SUM(CASE WHEN o.financial_status IN ('refunded', 'partially_refunded') THEN 1 ELSE 0 END) AS total_returned,
            ROUND(
                SUM(CASE WHEN o.financial_status IN ('refunded', 'partially_refunded') THEN 1 ELSE 0 END)::NUMERIC
                / NULLIF(COUNT(oi.id), 0), 4
            ) AS return_rate
        FROM order_items oi
        JOIN orders o ON o.store_id = oi.store_id AND o.id = oi.order_id
        JOIN products p ON p.store_id = oi.store_id AND p.id = oi.product_id
        WHERE oi.store_id = %(store_id)s
        GROUP BY oi.product_id, p.title, p.vendor
        HAVING
            ROUND(
                SUM(CASE WHEN o.financial_status IN ('refunded', 'partially_refunded') THEN 1 ELSE 0 END)::NUMERIC
                / NULLIF(COUNT(oi.id), 0), 4
            ) >= %(threshold)s
        ORDER BY return_rate DESC;
    """
    with get_cursor() as cursor:
        cursor.execute(sql, {"store_id": store_id, "threshold": constants.HIGH_RETURN_RATE_THRESHOLD})
        results = cursor.fetchall()

    logger.info(f"Found {len(results)} products with high return rate.")
    return [dict(r) for r in results]


def get_revenue_by_product(store_id: int) -> list[dict]:
    """
    Returns total revenue per product across all paid orders.
    """
    sql = """
        SELECT
            oi.product_id,
            p.title AS product_title,
            p.vendor,
            SUM(oi.quantity) AS total_units_sold,
            SUM(oi.quantity * oi.price) AS gross_revenue,
            SUM(oi.total_discount) AS total_discounts,
            SUM(oi.quantity * oi.price) - SUM(oi.total_discount) AS net_revenue
        FROM order_items oi
        JOIN orders o ON o.store_id = oi.store_id AND o.id = oi.order_id
        JOIN products p ON p.store_id = oi.store_id AND p.id = oi.product_id
        WHERE oi.store_id = %(store_id)s
          AND o.financial_status = 'paid'
        GROUP BY oi.product_id, p.title, p.vendor
        ORDER BY net_revenue DESC;
    """
    with get_cursor() as cursor:
        cursor.execute(sql, {"store_id": store_id})
        results = cursor.fetchall()

    logger.info(f"Revenue calculated for {len(results)} products.")
    return [dict(r) for r in results]


def get_revenue_summary(store_id: int) -> dict:
    """
    Returns a high-level revenue summary across all paid orders.
    """
    sql = """
        SELECT
            COUNT(DISTINCT o.id) AS total_orders,
            COUNT(DISTINCT o.customer_id) AS unique_customers,
            SUM(o.total_price) AS gross_revenue,
            SUM(o.total_discounts) AS total_discounts,
            SUM(o.total_price) - SUM(o.total_discounts) AS net_revenue,
            ROUND(AVG(o.total_price), 2) AS avg_order_value
        FROM orders o
        WHERE o.store_id = %(store_id)s
          AND o.financial_status = 'paid';
    """
    with get_cursor() as cursor:
        cursor.execute(sql, {"store_id": store_id})
        result = cursor.fetchone()

    logger.info("Revenue summary calculated.")
    return dict(result) if result else {}


def get_order_volume_trend(store_id: int) -> dict:
    """
    Compares paid order count in the last 7 days vs the previous 7 days.
    """
    sql = """
        SELECT
            SUM(
                CASE
                    WHEN o.created_at >= NOW() - INTERVAL '7 days' THEN 1
                    ELSE 0
                END
            ) AS current_7d_orders,
            SUM(
                CASE
                    WHEN o.created_at >= NOW() - INTERVAL '14 days'
                     AND o.created_at < NOW() - INTERVAL '7 days' THEN 1
                    ELSE 0
                END
            ) AS previous_7d_orders
        FROM orders o
        WHERE o.store_id = %(store_id)s
          AND o.financial_status = 'paid';
    """
    with get_cursor() as cursor:
        cursor.execute(sql, {"store_id": store_id})
        result = cursor.fetchone()

    payload = dict(result) if result else {}
    current_7d = int(payload.get("current_7d_orders") or 0)
    previous_7d = int(payload.get("previous_7d_orders") or 0)
    payload["delta_orders"] = current_7d - previous_7d
    return payload


def get_revenue_trend_7d(store_id: int) -> dict:
    """
    Compares paid net revenue (total_price - total_discounts) in the last 7 days
    vs the previous 7 days.
    """
    sql = """
        SELECT
            COALESCE(SUM(
                CASE
                    WHEN o.created_at >= NOW() - INTERVAL '7 days'
                    THEN (o.total_price - o.total_discounts)
                    ELSE 0
                END
            ), 0) AS current_7d_net_revenue,
            COALESCE(SUM(
                CASE
                    WHEN o.created_at >= NOW() - INTERVAL '14 days'
                     AND o.created_at < NOW() - INTERVAL '7 days'
                    THEN (o.total_price - o.total_discounts)
                    ELSE 0
                END
            ), 0) AS previous_7d_net_revenue
        FROM orders o
        WHERE o.store_id = %(store_id)s
          AND o.financial_status = 'paid';
    """
    with get_cursor() as cursor:
        cursor.execute(sql, {"store_id": store_id})
        result = cursor.fetchone()

    payload = dict(result) if result else {}
    current = float(payload.get("current_7d_net_revenue") or 0.0)
    previous = float(payload.get("previous_7d_net_revenue") or 0.0)
    payload["current_7d_net_revenue"] = current
    payload["previous_7d_net_revenue"] = previous
    payload["delta_net_revenue"] = current - previous
    if previous > 0:
        payload["delta_pct"] = (current - previous) / previous * 100.0
    return payload