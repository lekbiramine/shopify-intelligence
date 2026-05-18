from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor


ACTION_TYPE = "review_count_too_low"


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
            WITH orders_90d AS (
                SELECT o.id
                FROM orders o
                WHERE o.store_id = %(store_id)s
                  AND o.created_at >= NOW() - INTERVAL '90 days'
                  AND LOWER(COALESCE(o.financial_status, '')) IN ('paid', 'partially_refunded')
            ),
            product_sales AS (
                SELECT
                    oi.product_id,
                    COALESCE(SUM(COALESCE(oi.quantity, 0)), 0) AS units_sold
                FROM order_items oi
                JOIN orders_90d o ON o.id = oi.order_id
                WHERE oi.store_id = %(store_id)s
                GROUP BY oi.product_id
            ),
            return_signal AS (
                SELECT COUNT(*)::int AS returned_lines
                FROM order_items oi
                JOIN orders o ON o.store_id = oi.store_id AND o.id = oi.order_id
                WHERE oi.store_id = %(store_id)s
                  AND o.created_at >= NOW() - INTERVAL '90 days'
                  AND LOWER(COALESCE(o.financial_status, '')) IN ('refunded', 'partially_refunded')
            ),
            order_stats AS (
                SELECT COALESCE(COUNT(*), 0) AS total_orders
                FROM orders_90d
            ),
            top_sales AS (
                SELECT COALESCE(MAX(units_sold), 0) AS top_product_units
                FROM product_sales
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
                os.total_orders,
                COALESCE(ts.top_product_units, 0) AS top_product_units,
                COALESCE(rs.returned_lines, 0) AS returned_lines,
                COALESCE(rv.monthly_revenue, 0) AS monthly_revenue,
                COALESCE(sa.store_aov, 0) AS store_aov
            FROM order_stats os
            CROSS JOIN top_sales ts
            CROSS JOIN return_signal rs
            CROSS JOIN revenue_30d rv
            CROSS JOIN store_aov_metric sa;
            """,
            {"store_id": store_id},
        )
        row = cursor.fetchone() or {}
    finally:
        if should_close:
            cursor.close()

    total_orders = int(row.get("total_orders") or 0)
    top_product_units = int(row.get("top_product_units") or 0)
    returned_lines = int(row.get("returned_lines") or 0)
    monthly_revenue = float(row.get("monthly_revenue") or 0.0)
    store_aov = float(row.get("store_aov") or 0.0)

    has_high_sales_no_feedback = top_product_units >= 10 and returned_lines == 0
    if not (total_orders >= 50 and has_high_sales_no_feedback):
        return {"detected": False}

    review_opportunity = monthly_revenue * 0.12
    daily_impact = review_opportunity / 30.0
    seven_day_projection = daily_impact * 7.0

    return {
        "action_type": ACTION_TYPE,
        "detected": True,
        "metrics": {
            "total_orders": total_orders,
            "store_aov": store_aov,
            "monthly_revenue": monthly_revenue,
            "review_opportunity": review_opportunity,
        },
        "daily_impact": daily_impact,
        "total_value": review_opportunity,
        "seven_day_projection": seven_day_projection,
        "problem": (
            f"{total_orders} fulfilled orders in 90 days — "
            "no systematic review collection pattern detected"
        ),
        "fix": (
            "Automate post-delivery review requests and incentivize top customers"
        ),
        "impact_bullets": [
            f"Review-driven conversion lift opportunity: ${review_opportunity:,.2f}/month",
            f"Top SKU moved {top_product_units} units without feedback loop",
        ],
        "risk_bullets": [
            "New visitors see empty social proof and bounce",
            "Competitors with reviews win same-intent traffic",
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
