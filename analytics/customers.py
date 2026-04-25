from db.connection import get_cursor
from config import constants
from config.logging_config import get_logger

logger = get_logger(__name__)


def _get_customers_by_days_since_order(store_id: int, days: int) -> list[dict]:
    """
    Generic query — returns customers whose last order was more than `days` ago.
    Includes customers with no orders (treated as highly churned).
    """
    sql = """
        SELECT
            c.id AS customer_id,
            c.email,
            c.first_name,
            c.last_name,
            c.orders_count,
            c.total_spent,
            MAX(o.created_at) AS last_order_date,
            CASE
                WHEN MAX(o.created_at) IS NULL THEN NULL
                ELSE EXTRACT(EPOCH FROM NOW() - MAX(o.created_at)) / 86400
            END AS days_since_last_order
        FROM customers c
        LEFT JOIN orders o ON o.store_id = c.store_id AND o.customer_id = c.id
        WHERE c.store_id = %(store_id)s
        GROUP BY c.id, c.email, c.first_name, c.last_name, c.orders_count, c.total_spent
        HAVING
            (
                MAX(o.created_at) IS NULL
                OR EXTRACT(EPOCH FROM NOW() - MAX(o.created_at)) / 86400 >= %(days)s
            )
        ORDER BY days_since_last_order DESC NULLS FIRST;
    """
    with get_cursor() as cursor:
        cursor.execute(sql, {"store_id": store_id, "days": days})
        results = cursor.fetchall()

    return [dict(r) for r in results]


def get_churned_customers(store_id: int) -> list[dict]:
    """
    Returns customers who haven't ordered in CHURN_DAYS_THRESHOLD days
    OR never ordered at all.
    """
    results = _get_customers_by_days_since_order(store_id, constants.CHURN_DAYS_THRESHOLD)
    logger.info(f"Found {len(results)} churned customers.")
    return results


def get_loyal_customers(store_id: int) -> list[dict]:
    """
    Returns customers with orders_count >= HIGH_VALUE_ORDER_COUNT.
    """
    sql = """
        SELECT
            c.id AS customer_id,
            c.email,
            c.first_name,
            c.last_name,
            c.orders_count,
            c.total_spent
        FROM customers c
        WHERE c.store_id = %(store_id)s
          AND c.orders_count >= %(min_orders)s
        ORDER BY c.total_spent DESC;
    """
    with get_cursor() as cursor:
        cursor.execute(sql, {"store_id": store_id, "min_orders": constants.HIGH_VALUE_ORDER_COUNT})
        results = cursor.fetchall()

    logger.info(f"Found {len(results)} loyal customers.")
    return [dict(r) for r in results]


def get_never_returned_customers(store_id: int) -> list[dict]:
    """
    Returns customers who placed exactly one order and never came back.
    """
    sql = """
        SELECT
            c.id AS customer_id,
            c.email,
            c.first_name,
            c.last_name,
            c.orders_count,
            c.total_spent,
            MAX(o.created_at) AS last_order_date
        FROM customers c
        LEFT JOIN orders o ON o.store_id = c.store_id AND o.customer_id = c.id
        WHERE c.store_id = %(store_id)s
          AND c.orders_count = 1
        GROUP BY c.id, c.email, c.first_name, c.last_name, c.orders_count, c.total_spent
        ORDER BY last_order_date DESC;
    """
    with get_cursor() as cursor:
        cursor.execute(sql, {"store_id": store_id})
        results = cursor.fetchall()

    logger.info(f"Found {len(results)} one-time customers.")
    return [dict(r) for r in results]


def get_customer_health_metrics(store_id: int) -> dict:
    """
    Returns lightweight customer health KPIs for decision-focused reporting.
    """
    sql = """
        WITH repeat_30d AS (
            SELECT
                o.customer_id
            FROM orders o
            WHERE o.store_id = %(store_id)s
              AND o.created_at >= NOW() - INTERVAL '30 days'
            GROUP BY o.customer_id
            HAVING COUNT(*) >= 2
        )
        SELECT
            COALESCE(SUM(CASE WHEN c.orders_count >= 2 THEN 1 ELSE 0 END), 0) AS repeat_customer_count,
            COALESCE(COUNT(r.customer_id), 0) AS repeat_customers_last_30d,
            COALESCE(SUM(CASE WHEN (c.first_name IS NULL OR TRIM(c.first_name) = '')
                               AND (c.last_name IS NULL OR TRIM(c.last_name) = '')
                               AND (c.email IS NULL OR TRIM(c.email) = '') THEN 1 ELSE 0 END), 0) AS unidentified_customers
        FROM customers c
        LEFT JOIN repeat_30d r ON r.customer_id = c.id
        WHERE c.store_id = %(store_id)s;
    """
    with get_cursor() as cursor:
        cursor.execute(sql, {"store_id": store_id})
        result = cursor.fetchone()

    payload = dict(result) if result else {}
    return {
        "repeat_customer_count": int(payload.get("repeat_customer_count") or 0),
        "repeat_customers_last_30d": int(payload.get("repeat_customers_last_30d") or 0),
        "unidentified_customers": int(payload.get("unidentified_customers") or 0),
    }