from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor


ACTION_TYPE = "no_email_automation_flows"


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
                    COUNT(*) AS order_count
                FROM orders o
                WHERE o.store_id = %(store_id)s
                  AND o.customer_id IS NOT NULL
                  AND LOWER(COALESCE(o.financial_status, '')) IN ('paid', 'partially_refunded')
                GROUP BY o.customer_id
            ),
            customer_stats AS (
                SELECT
                    COALESCE(COUNT(*), 0) AS total_customers,
                    COALESCE(SUM(CASE WHEN order_count >= 2 THEN 1 ELSE 0 END), 0) AS repeat_customers,
                    COALESCE(SUM(CASE WHEN order_count = 1 THEN 1 ELSE 0 END), 0) AS one_time_buyers
                FROM customer_orders
            ),
            winback_orders AS (
                SELECT COUNT(*)::int AS winback_count
                FROM (
                    SELECT o.customer_id
                    FROM orders o
                    WHERE o.store_id = %(store_id)s
                      AND o.created_at >= NOW() - INTERVAL '30 days'
                      AND LOWER(COALESCE(o.financial_status, '')) IN ('paid', 'partially_refunded')
                      AND o.customer_id IS NOT NULL
                      AND EXISTS (
                          SELECT 1
                          FROM orders prev
                          WHERE prev.store_id = o.store_id
                            AND prev.customer_id = o.customer_id
                            AND prev.created_at < o.created_at - INTERVAL '60 days'
                            AND LOWER(COALESCE(prev.financial_status, '')) IN ('paid', 'partially_refunded')
                      )
                    GROUP BY o.customer_id
                ) w
            ),
            store_aov_metric AS (
                SELECT COALESCE(AVG(COALESCE(o.total_price, 0)), 0) AS store_aov
                FROM orders o
                WHERE o.store_id = %(store_id)s
                  AND o.created_at >= NOW() - INTERVAL '90 days'
                  AND LOWER(COALESCE(o.financial_status, '')) IN ('paid', 'partially_refunded')
            )
            SELECT
                cs.total_customers,
                cs.repeat_customers,
                cs.one_time_buyers,
                COALESCE(w.winback_count, 0) AS winback_count,
                COALESCE(sa.store_aov, 0) AS store_aov
            FROM customer_stats cs
            CROSS JOIN winback_orders w
            CROSS JOIN store_aov_metric sa;
            """,
            {"store_id": store_id},
        )
        row = cursor.fetchone() or {}
    finally:
        if should_close:
            cursor.close()

    total_customers = int(row.get("total_customers") or 0)
    repeat_customers = int(row.get("repeat_customers") or 0)
    one_time_buyers = int(row.get("one_time_buyers") or 0)
    winback_count = int(row.get("winback_count") or 0)
    store_aov = float(row.get("store_aov") or 0.0)
    repeat_rate = (repeat_customers / total_customers) if total_customers > 0 else 0.0

    if not (total_customers >= 100 and repeat_rate < 0.30 and winback_count == 0):
        return {"detected": False}

    winback_opportunity = one_time_buyers * store_aov * 0.08
    daily_impact = winback_opportunity / 30.0
    seven_day_projection = daily_impact * 7.0

    return {
        "action_type": ACTION_TYPE,
        "detected": True,
        "metrics": {
            "total_customers": total_customers,
            "one_time_buyers": one_time_buyers,
            "repeat_rate": repeat_rate,
            "store_aov": store_aov,
            "winback_opportunity": winback_opportunity,
        },
        "daily_impact": daily_impact,
        "total_value": winback_opportunity,
        "seven_day_projection": seven_day_projection,
        "problem": (
            f"{one_time_buyers} one-time buyers — only {repeat_rate * 100:.1f}% "
            "repeat rate and no win-back orders in 30 days"
        ),
        "fix": (
            "Build abandoned-cart, win-back, post-purchase, and welcome email flows"
        ),
        "impact_bullets": [
            f"Win-back opportunity: ${winback_opportunity:,.2f}",
            f"{total_customers} customers in database with weak automation",
        ],
        "risk_bullets": [
            "One-time buyers decay without automated nurture",
            "Broadcast-only email underperforms flows by 18x per send",
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
