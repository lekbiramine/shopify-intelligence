from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor


ACTION_TYPE = "no_subscription_revenue"


def _get_cursor(db: Any):
    if hasattr(db, "execute"):
        return db, False
    if hasattr(db, "cursor"):
        return db.cursor(cursor_factory=RealDictCursor), True
    raise TypeError("db must be a DB cursor or psycopg2 connection")


def run_insight(db: Any, *, store_id: int) -> dict:
    cursor, should_close = _get_cursor(db)
    try:
        cursor.execute(
            """
            WITH customer_product_orders AS (
                SELECT
                    o.customer_id,
                    oi.product_id,
                    COUNT(*) AS purchase_count
                FROM orders o
                JOIN order_items oi ON oi.store_id = o.store_id AND oi.order_id = o.id
                WHERE o.store_id = %(store_id)s
                  AND o.customer_id IS NOT NULL
                  AND LOWER(COALESCE(o.financial_status, '')) IN ('paid', 'partially_refunded')
                GROUP BY o.customer_id, oi.product_id
                HAVING COUNT(*) >= 2
            ),
            repeat_stats AS (
                SELECT
                    COALESCE(COUNT(*), 0) AS total_repeat_orders,
                    COALESCE(COUNT(DISTINCT customer_id), 0) AS repeat_buyers
                FROM customer_product_orders
            ),
            customer_base AS (
                SELECT COUNT(DISTINCT o.customer_id) AS total_customers
                FROM orders o
                WHERE o.store_id = %(store_id)s
                  AND o.customer_id IS NOT NULL
                  AND LOWER(COALESCE(o.financial_status, '')) IN ('paid', 'partially_refunded')
            ),
            subscription_proxy AS (
                SELECT COUNT(*)::int AS subscription_like_orders
                FROM order_items oi
                JOIN orders o ON o.store_id = oi.store_id AND o.id = oi.order_id
                WHERE oi.store_id = %(store_id)s
                  AND LOWER(COALESCE(o.financial_status, '')) IN ('paid', 'partially_refunded')
                  AND (
                      LOWER(COALESCE(oi.title, '')) LIKE '%%subscribe%%'
                      OR LOWER(COALESCE(oi.title, '')) LIKE '%%subscription%%'
                      OR LOWER(COALESCE(oi.title, '')) LIKE '%%recurring%%'
                  )
            ),
            revenue_30d AS (
                SELECT COALESCE(SUM(COALESCE(o.total_price, 0)), 0) AS monthly_revenue
                FROM orders o
                WHERE o.store_id = %(store_id)s
                  AND o.created_at >= NOW() - INTERVAL '30 days'
                  AND LOWER(COALESCE(o.financial_status, '')) IN ('paid', 'partially_refunded')
            ),
            store_aov_metric AS (
                SELECT COALESCE(AVG(COALESCE(o.total_price, 0)), 0) AS store_aov
                FROM orders o
                WHERE o.store_id = %(store_id)s
                  AND o.created_at >= NOW() - INTERVAL '90 days'
                  AND LOWER(COALESCE(o.financial_status, '')) IN ('paid', 'partially_refunded')
            )
            SELECT
                rs.total_repeat_orders,
                rs.repeat_buyers,
                cb.total_customers,
                COALESCE(sp.subscription_like_orders, 0) AS subscription_like_orders,
                COALESCE(rv.monthly_revenue, 0) AS monthly_revenue,
                COALESCE(sa.store_aov, 0) AS store_aov
            FROM repeat_stats rs
            CROSS JOIN customer_base cb
            CROSS JOIN subscription_proxy sp
            CROSS JOIN revenue_30d rv
            CROSS JOIN store_aov_metric sa;
            """,
            {"store_id": store_id},
        )
        row = cursor.fetchone() or {}
    finally:
        if should_close:
            cursor.close()

    total_repeat_orders = int(row.get("total_repeat_orders") or 0)
    repeat_buyers = int(row.get("repeat_buyers") or 0)
    total_customers = int(row.get("total_customers") or 0)
    subscription_like_orders = int(row.get("subscription_like_orders") or 0)
    monthly_revenue = float(row.get("monthly_revenue") or 0.0)
    store_aov = float(row.get("store_aov") or 0.0)
    repeat_rate = (repeat_buyers / total_customers) if total_customers > 0 else 0.0

    if not (
        repeat_rate > 0.25
        and total_repeat_orders >= 10
        and subscription_like_orders == 0
    ):
        return {"detected": False}

    subscription_opportunity = monthly_revenue * 0.25
    daily_impact = subscription_opportunity / 30.0
    seven_day_projection = daily_impact * 7.0

    return {
        "action_type": ACTION_TYPE,
        "detected": True,
        "metrics": {
            "repeat_rate": repeat_rate,
            "total_repeat_orders": total_repeat_orders,
            "store_aov": store_aov,
            "monthly_revenue": monthly_revenue,
            "subscription_opportunity": subscription_opportunity,
        },
        "daily_impact": daily_impact,
        "total_value": subscription_opportunity,
        "seven_day_projection": seven_day_projection,
        "problem": (
            f"{repeat_rate * 100:.1f}% repeat-buyer rate on same SKUs — "
            f"{total_repeat_orders} manual repeat orders, no subscription revenue"
        ),
        "fix": (
            "Offer Subscribe & Save 15% on top repeat-purchase products"
        ),
        "impact_bullets": [
            f"Subscription opportunity: ${subscription_opportunity:,.2f}/month",
            f"{total_repeat_orders} repeat SKU orders without autopay",
        ],
        "risk_bullets": [
            "Repeat buyers may churn to competitors with subscriptions",
            "Manual reorders are forgotten and unpredictable",
        ],
        "targets": [],
        "state": "pending",
    }


def _load_env_value(key: str, env_path: Path) -> str:
    if not env_path.exists():
        return ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        if name.strip() == key:
            return value.strip().strip('"').strip("'")
    return ""


if __name__ == "__main__":
    env_file = Path(__file__).resolve().parents[2] / ".env"
    dsn = _load_env_value("DATABASE_URL", env_file) or _load_env_value("DB_DSN", env_file)
    if not dsn:
        raise RuntimeError("Missing DATABASE_URL or DB_DSN in .env")
    with psycopg2.connect(dsn) as conn:
        print(run_insight(conn, store_id=1))
