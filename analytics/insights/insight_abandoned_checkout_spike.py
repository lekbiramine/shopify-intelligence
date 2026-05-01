from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor


ACTION_TYPE = "abandoned_checkout_spike"


def _get_cursor(db: Any):
    if hasattr(db, "execute"):
        return db, False
    if hasattr(db, "cursor"):
        return db.cursor(cursor_factory=RealDictCursor), True
    raise TypeError("db must be a DB cursor or psycopg2 connection")


def run_insight(db: Any) -> dict:
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
                    COALESCE(SUM(CASE WHEN created_at >= NOW() - INTERVAL '7 days' THEN 1 ELSE 0 END), 0) AS current_week,
                    COALESCE(SUM(CASE WHEN created_at >= NOW() - INTERVAL '14 days'
                                      AND created_at < NOW() - INTERVAL '7 days' THEN 1 ELSE 0 END), 0) AS prev_week
                FROM abandoned_checkouts
            ),
            orders AS (
                SELECT
                    COALESCE(SUM(CASE WHEN created_at >= NOW() - INTERVAL '7 days'
                                      AND COALESCE(financial_status, '') NOT IN ('voided', 'cancelled')
                                      THEN 1 ELSE 0 END), 0) AS completed_orders_this_week,
                    COALESCE(SUM(CASE WHEN created_at >= NOW() - INTERVAL '14 days'
                                      AND created_at < NOW() - INTERVAL '7 days'
                                      AND COALESCE(financial_status, '') NOT IN ('voided', 'cancelled')
                                      THEN 1 ELSE 0 END), 0) AS completed_orders_prev_week
                FROM orders
            ),
            aov AS (
                SELECT
                    COALESCE(AVG(COALESCE(total_price, 0)), 0) AS store_aov
                FROM orders
                WHERE created_at >= NOW() - INTERVAL '90 days'
                  AND COALESCE(financial_status, '') NOT IN ('voided', 'cancelled')
            )
            SELECT
                COALESCE(a.current_week, 0) AS abandoned_count,
                COALESCE(a.prev_week, 0) AS prev_week_abandoned_count,
                COALESCE(o.completed_orders_this_week, 0) AS completed_orders_this_week,
                COALESCE(o.completed_orders_prev_week, 0) AS completed_orders_prev_week,
                COALESCE(s.store_aov, 0) AS store_aov
            FROM abandon a
            CROSS JOIN orders o
            CROSS JOIN aov s;
            """
        )
        row = cursor.fetchone() or {}
    finally:
        if should_close:
            cursor.close()

    abandoned_count = int(row.get("abandoned_count") or 0)
    prev_week_abandoned_count = int(row.get("prev_week_abandoned_count") or 0)
    completed_orders_this_week = int(row.get("completed_orders_this_week") or 0)
    completed_orders_prev_week = int(row.get("completed_orders_prev_week") or 0)
    store_aov = float(row.get("store_aov") or 0.0)

    current_denominator = abandoned_count + completed_orders_this_week
    prev_denominator = prev_week_abandoned_count + completed_orders_prev_week
    abandonment_rate = (abandoned_count / current_denominator) if current_denominator > 0 else 0.0
    prev_week_abandonment_rate = (
        prev_week_abandoned_count / prev_denominator if prev_denominator > 0 else 0.0
    )

    spike_detected = (
        abandoned_count > (prev_week_abandoned_count * 1.25)
        if prev_week_abandoned_count > 0
        else abandoned_count > 0
    )
    if not (abandonment_rate > 0.70 or spike_detected):
        return {"detected": False}

    potential_revenue = abandoned_count * store_aov
    daily_impact = (potential_revenue * 0.15) / 7.0
    seven_day_projection = daily_impact * 7.0

    return {
        "action_type": ACTION_TYPE,
        "detected": True,
        "metrics": {
            "abandoned_count": abandoned_count,
            "abandonment_rate": abandonment_rate,
            "potential_revenue": potential_revenue,
            "store_aov": store_aov,
            "prev_week_abandonment_rate": prev_week_abandonment_rate,
        },
        "daily_impact": daily_impact,
        "total_value": potential_revenue,
        "seven_day_projection": seven_day_projection,
        "problem": (
            f"{abandoned_count} checkouts abandoned this week — "
            f"${potential_revenue:.2f} left at the door"
        ),
        "fix": (
            "Send a 2-email abandoned cart sequence: immediate recovery "
            "email at 1 hour, discount offer at 24 hours"
        ),
        "impact_bullets": [
            "A 15% recovery benchmark is realistic for targeted abandoned-cart flows",
            f"Current abandonment rate is {abandonment_rate * 100:.1f}% this week",
        ],
        "risk_bullets": [
            "Checkout friction can suppress paid traffic ROI in less than a week",
            "Unrecovered carts usually decay in conversion probability after 24 hours",
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
