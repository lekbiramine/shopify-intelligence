from db.connection import get_cursor
from config import constants
from config.logging_config import get_logger

logger = get_logger(__name__)


def _get_customers_by_days_since_order(days: int) -> list[dict]:
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
        LEFT JOIN orders o ON o.customer_id = c.id
        GROUP BY c.id, c.email, c.first_name, c.last_name, c.orders_count, c.total_spent
        HAVING
            (
                MAX(o.created_at) IS NULL
                OR EXTRACT(EPOCH FROM NOW() - MAX(o.created_at)) / 86400 >= %(days)s
            )
        ORDER BY days_since_last_order DESC NULLS FIRST;
    """
    with get_cursor() as cursor:
        cursor.execute(sql, {"days": days})
        results = cursor.fetchall()

    return [dict(r) for r in results]


def get_churned_customers() -> list[dict]:
    """
    Returns customers who haven't ordered in CHURN_DAYS_THRESHOLD days
    OR never ordered at all.
    """
    results = _get_customers_by_days_since_order(constants.CHURN_DAYS_THRESHOLD)
    logger.info(f"Found {len(results)} churned customers.")
    return results


def get_loyal_customers() -> list[dict]:
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
        WHERE c.orders_count >= %(min_orders)s
        ORDER BY c.total_spent DESC;
    """
    with get_cursor() as cursor:
        cursor.execute(sql, {"min_orders": constants.HIGH_VALUE_ORDER_COUNT})
        results = cursor.fetchall()

    logger.info(f"Found {len(results)} loyal customers.")
    return [dict(r) for r in results]


def get_never_returned_customers() -> list[dict]:
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
        LEFT JOIN orders o ON o.customer_id = c.id
        WHERE c.orders_count = 1
        GROUP BY c.id, c.email, c.first_name, c.last_name, c.orders_count, c.total_spent
        ORDER BY last_order_date DESC;
    """
    with get_cursor() as cursor:
        cursor.execute(sql)
        results = cursor.fetchall()

    logger.info(f"Found {len(results)} one-time customers.")
    return [dict(r) for r in results]