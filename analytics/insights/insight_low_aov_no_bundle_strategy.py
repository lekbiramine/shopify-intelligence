from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor


ACTION_TYPE = "low_aov_no_bundle_strategy"


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
            WITH paid_orders_30d AS (
                SELECT o.id, COALESCE(o.total_price, 0) AS total_price
                FROM orders o
                WHERE o.store_id = %(store_id)s
                  AND o.created_at >= NOW() - INTERVAL '30 days'
                  AND LOWER(COALESCE(o.financial_status, '')) IN ('paid', 'partially_refunded')
            ),
            order_item_units AS (
                SELECT
                    oi.order_id,
                    COALESCE(SUM(COALESCE(oi.quantity, 0)), 0) AS item_units
                FROM order_items oi
                INNER JOIN paid_orders_30d po ON po.id = oi.order_id
                WHERE oi.store_id = %(store_id)s
                GROUP BY oi.order_id
            ),
            metrics AS (
                SELECT
                    COALESCE(COUNT(*), 0) AS total_orders,
                    COALESCE(AVG(po.total_price), 0) AS store_aov,
                    COALESCE(SUM(po.total_price), 0) AS monthly_revenue,
                    COALESCE(AVG(COALESCE(oiu.item_units, 0)), 0) AS avg_items_per_order
                FROM paid_orders_30d po
                LEFT JOIN order_item_units oiu ON oiu.order_id = po.id
            )
            SELECT * FROM metrics;
            """,
            {"store_id": store_id},
        )
        row = cursor.fetchone() or {}
    finally:
        if should_close:
            cursor.close()

    total_orders = int(row.get("total_orders") or 0)
    store_aov = float(row.get("store_aov") or 0.0)
    monthly_revenue = float(row.get("monthly_revenue") or 0.0)
    avg_items_per_order = float(row.get("avg_items_per_order") or 0.0)

    if not (store_aov < 45.0 and total_orders >= 20 and avg_items_per_order < 1.3):
        return {"detected": False}

    bundle_opportunity = monthly_revenue * 0.20
    daily_impact = bundle_opportunity / 30.0
    seven_day_projection = daily_impact * 7.0

    return {
        "action_type": ACTION_TYPE,
        "detected": True,
        "metrics": {
            "store_aov": store_aov,
            "total_orders": total_orders,
            "monthly_revenue": monthly_revenue,
            "bundle_opportunity": bundle_opportunity,
            "avg_items_per_order": avg_items_per_order,
        },
        "daily_impact": daily_impact,
        "total_value": bundle_opportunity,
        "seven_day_projection": seven_day_projection,
        "problem": (
            f"AOV ${store_aov:.2f} with {avg_items_per_order:.1f} items/order — "
            "no bundle strategy lifting basket size"
        ),
        "fix": (
            "Launch bundles, free-shipping threshold, and quantity discounts"
        ),
        "impact_bullets": [
            f"Bundle/AOV opportunity: ${bundle_opportunity:,.2f}/month",
            f"{total_orders} orders/month at sub-industry AOV",
        ],
        "risk_bullets": [
            "Low AOV forces higher ad spend per dollar of revenue",
            "Every month at current AOV leaves margin on the table",
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
