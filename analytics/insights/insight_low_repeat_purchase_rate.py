from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor


ACTION_TYPE = "low_repeat_purchase_rate"


def _get_cursor(db: Any):
    if hasattr(db, "execute"):
        return db, False
    if hasattr(db, "cursor"):
        return db.cursor(cursor_factory=RealDictCursor), True
    raise TypeError("db must be a DB cursor or psycopg2 connection")


def run_insight(db: Any) -> dict:
    cursor, should_close = _get_cursor(db)
    try:
        cursor.execute(
            """
            WITH customer_order_counts AS (
                SELECT
                    o.customer_id,
                    COUNT(*) AS order_count_90d
                FROM orders o
                WHERE o.created_at >= NOW() - INTERVAL '90 days'
                  AND o.customer_id IS NOT NULL
                  AND COALESCE(o.financial_status, '') NOT IN ('voided', 'cancelled')
                GROUP BY o.customer_id
            ),
            order_metrics AS (
                SELECT
                    COALESCE(AVG(COALESCE(o.total_price, 0)), 0) AS store_aov
                FROM orders o
                WHERE o.created_at >= NOW() - INTERVAL '90 days'
                  AND COALESCE(o.financial_status, '') NOT IN ('voided', 'cancelled')
            )
            SELECT
                COALESCE(COUNT(*), 0) AS total_customers,
                COALESCE(SUM(CASE WHEN c.order_count_90d >= 2 THEN 1 ELSE 0 END), 0) AS repeat_customers,
                COALESCE(SUM(CASE WHEN c.order_count_90d = 1 THEN 1 ELSE 0 END), 0) AS one_time_buyers,
                COALESCE((SELECT store_aov FROM order_metrics), 0) AS store_aov
            FROM customer_order_counts c;
            """
        )
        row = cursor.fetchone() or {}
    finally:
        if should_close:
            cursor.close()

    total_customers = int(row.get("total_customers") or 0)
    repeat_customers = int(row.get("repeat_customers") or 0)
    one_time_buyers = int(row.get("one_time_buyers") or 0)
    store_aov = float(row.get("store_aov") or 0.0)
    repeat_rate = (repeat_customers / total_customers) if total_customers > 0 else 0.0

    if one_time_buyers <= 0:
        return {"detected": False}

    if not (repeat_rate < 0.20 and total_customers >= 10):
        return {"detected": False}

    revenue_if_10pct_improvement = one_time_buyers * 0.10 * store_aov
    daily_impact = revenue_if_10pct_improvement / 90.0
    total_value = revenue_if_10pct_improvement
    seven_day_projection = daily_impact * 7.0

    return {
        "action_type": ACTION_TYPE,
        "detected": True,
        "metrics": {
            "repeat_rate": repeat_rate,
            "total_customers": total_customers,
            "one_time_buyers": one_time_buyers,
            "store_aov": store_aov,
            "revenue_if_10pct_improvement": revenue_if_10pct_improvement,
        },
        "daily_impact": daily_impact,
        "total_value": total_value,
        "seven_day_projection": seven_day_projection,
        "problem": (
            f"Only {repeat_rate * 100:.1f}% of customers reorder — "
            f"{one_time_buyers} one-time buyers have never returned"
        ),
        "fix": (
            "Launch a 3-email post-purchase sequence targeting "
            "one-time buyers with a 10% loyalty discount"
        ),
        "impact_bullets": [
            f"Converting 10% of one-time buyers can add ${revenue_if_10pct_improvement:,.2f} in 90 days",
            f"Current repeat rate is {repeat_rate * 100:.1f}% across {total_customers} recent customers",
        ],
        "risk_bullets": [
            "One-time buyers increase paid acquisition dependency",
            "Low repeat behavior suppresses customer lifetime value growth",
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
        print(run_insight(conn))
