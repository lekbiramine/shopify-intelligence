from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor


ACTION_TYPE = "high_single_order_customer_ratio"


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
            WITH customer_orders AS (
                SELECT
                    o.customer_id,
                    COUNT(*) AS order_count,
                    COALESCE(SUM(COALESCE(o.total_price, 0)), 0) AS lifetime_spend
                FROM orders o
                WHERE o.store_id = %(store_id)s
                  AND o.customer_id IS NOT NULL
                  AND LOWER(COALESCE(o.financial_status, '')) IN ('paid', 'partially_refunded')
                GROUP BY o.customer_id
            ),
            stats AS (
                SELECT
                    COALESCE(COUNT(*), 0) AS total_customers,
                    COALESCE(SUM(CASE WHEN order_count = 1 THEN 1 ELSE 0 END), 0) AS one_time_buyers,
                    COALESCE(AVG(lifetime_spend), 0) AS actual_avg_ltv
                FROM customer_orders
            ),
            store_aov_metric AS (
                SELECT COALESCE(AVG(COALESCE(o.total_price, 0)), 0) AS store_aov
                FROM orders o
                WHERE o.store_id = %(store_id)s
                  AND o.created_at >= NOW() - INTERVAL '90 days'
                  AND LOWER(COALESCE(o.financial_status, '')) IN ('paid', 'partially_refunded')
            )
            SELECT
                s.total_customers,
                s.one_time_buyers,
                s.actual_avg_ltv,
                COALESCE(sa.store_aov, 0) AS store_aov
            FROM stats s
            CROSS JOIN store_aov_metric sa;
            """,
            {"store_id": store_id},
        )
        row = cursor.fetchone() or {}
    finally:
        if should_close:
            cursor.close()

    total_customers = int(row.get("total_customers") or 0)
    one_time_buyers = int(row.get("one_time_buyers") or 0)
    actual_avg_ltv = float(row.get("actual_avg_ltv") or 0.0)
    store_aov = float(row.get("store_aov") or 0.0)
    one_time_ratio = (one_time_buyers / total_customers) if total_customers > 0 else 0.0
    ltv_gap = store_aov * 3.0

    if not (total_customers >= 30 and one_time_ratio > 0.70):
        return {"detected": False}

    recovery_value = one_time_buyers * 0.10 * store_aov
    daily_impact = recovery_value / 30.0
    seven_day_projection = daily_impact * 7.0

    return {
        "action_type": ACTION_TYPE,
        "detected": True,
        "metrics": {
            "one_time_buyers": one_time_buyers,
            "total_customers": total_customers,
            "one_time_ratio": one_time_ratio,
            "store_aov": store_aov,
            "ltv_gap": ltv_gap,
            "actual_avg_ltv": actual_avg_ltv,
        },
        "daily_impact": daily_impact,
        "total_value": recovery_value,
        "seven_day_projection": seven_day_projection,
        "problem": (
            f"{one_time_ratio * 100:.1f}% of customers bought once — "
            f"{one_time_buyers} one-time buyers on an acquisition treadmill"
        ),
        "fix": (
            "Launch post-purchase email sequence and loyalty mechanic for 3rd purchase"
        ),
        "impact_bullets": [
            f"10% reactivation of one-time buyers ≈ ${recovery_value:,.2f}",
            f"Actual avg LTV ${actual_avg_ltv:.2f} vs target ${ltv_gap:.2f}",
        ],
        "risk_bullets": [
            "Paid acquisition must refill the bucket every month",
            "Back-end retention is underperforming vs acquisition spend",
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
