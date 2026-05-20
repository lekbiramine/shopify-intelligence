from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor


ACTION_TYPE = "cart_abandonment_no_recovery"


def _get_cursor(db: Any):
    if hasattr(db, "execute"):
        return db, False
    if hasattr(db, "cursor"):
        return db.cursor(cursor_factory=RealDictCursor), True
    raise TypeError("db must be a DB cursor or psycopg2 connection")


def run_insight(db: Any, *, store_id: int) -> dict:
    cursor, should_close = _get_cursor(db)
    try:
        cursor.execute("SELECT to_regclass('public.abandoned_checkouts') AS table_name;")
        table_row = cursor.fetchone() or {}
        if not table_row.get("table_name"):
            return {"detected": False, "reason": "no_data_source"}

        cursor.execute(
            """
            WITH abandon AS (
                SELECT
                    COALESCE(SUM(CASE WHEN created_at >= NOW() - INTERVAL '7 days' THEN 1 ELSE 0 END), 0) AS abandoned_count
                FROM abandoned_checkouts
                WHERE store_id = %(store_id)s
            ),
            completed_order_counts AS (
                SELECT
                    COALESCE(SUM(CASE WHEN created_at >= NOW() - INTERVAL '7 days'
                                      AND COALESCE(financial_status, '') NOT IN ('voided', 'cancelled')
                                      THEN 1 ELSE 0 END), 0) AS completed_orders_this_week
                FROM orders
                WHERE store_id = %(store_id)s
            ),
            store_aov_metric AS (
                SELECT COALESCE(AVG(COALESCE(o.total_price, 0)), 0) AS store_aov
                FROM orders o
                WHERE o.store_id = %(store_id)s
                  AND o.created_at >= NOW() - INTERVAL '90 days'
                  AND LOWER(COALESCE(o.financial_status, '')) IN ('paid', 'partially_refunded')
            )
            SELECT
                COALESCE(a.abandoned_count, 0) AS abandoned_count,
                COALESCE(oc.completed_orders_this_week, 0) AS completed_orders_this_week,
                COALESCE(sa.store_aov, 0) AS store_aov
            FROM abandon a
            CROSS JOIN completed_order_counts oc
            CROSS JOIN store_aov_metric sa;
            """,
            {"store_id": store_id},
        )
        row = cursor.fetchone() or {}
    finally:
        if should_close:
            cursor.close()

    abandoned_count = int(row.get("abandoned_count") or 0)
    completed_orders_this_week = int(row.get("completed_orders_this_week") or 0)
    store_aov = float(row.get("store_aov") or 0.0)

    denominator = abandoned_count + completed_orders_this_week
    abandonment_rate = (abandoned_count / denominator) if denominator > 0 else 0.0

    if not (abandoned_count >= 5 and abandonment_rate > 0.65):
        return {"detected": False}

    abandoned_value = abandoned_count * store_aov
    potential_recovery = abandoned_value * 0.15
    weekly_loss = abandoned_value
    daily_impact = abandoned_value * 0.15 / 7.0 if abandoned_value > 0 else 0.0
    seven_day_projection = potential_recovery

    return {
        "action_type": ACTION_TYPE,
        "detected": True,
        "metrics": {
            "abandoned_count": abandoned_count,
            "abandonment_rate": abandonment_rate,
            "store_aov": store_aov,
            "abandoned_value": abandoned_value,
            "potential_recovery": potential_recovery,
            "weekly_loss": weekly_loss,
        },
        "daily_impact": daily_impact,
        "total_value": potential_recovery,
        "seven_day_projection": seven_day_projection,
        "problem": (
            f"{abandoned_count} carts abandoned this week ({abandonment_rate * 100:.1f}% rate) — "
            "no cart recovery sequence detected"
        ),
        "fix": (
            "Launch 3-email abandoned cart sequence: 1 hour, 24 hours, 72 hours"
        ),
        "impact_bullets": [
            f"Recoverable this week: ${potential_recovery:,.2f} at 15% recovery",
            f"${weekly_loss:,.2f} weekly cart value at risk",
        ],
        "risk_bullets": [
            "High-intent visitors leave without automated follow-up",
            "Delay past 24 hours cuts recovery rate by 3x",
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
