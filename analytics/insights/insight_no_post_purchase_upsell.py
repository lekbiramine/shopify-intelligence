from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor


ACTION_TYPE = "no_post_purchase_upsell"


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
                SELECT o.id
                FROM orders o
                WHERE o.store_id = %(store_id)s
                  AND o.created_at >= NOW() - INTERVAL '30 days'
                  AND LOWER(COALESCE(o.financial_status, '')) IN ('paid', 'partially_refunded')
            ),
            order_line_stats AS (
                SELECT
                    oi.order_id,
                    COUNT(*)::int AS line_count,
                    COALESCE(SUM(COALESCE(oi.quantity, 0)), 0)::numeric AS item_units
                FROM order_items oi
                INNER JOIN paid_orders_30d po ON po.id = oi.order_id
                WHERE oi.store_id = %(store_id)s
                GROUP BY oi.order_id
            ),
            order_metrics AS (
                SELECT
                    COALESCE(COUNT(*), 0) AS total_orders,
                    COALESCE(AVG(COALESCE(ols.item_units, 0)), 0) AS avg_items_per_order,
                    COALESCE(SUM(CASE WHEN COALESCE(ols.line_count, 0) = 1 THEN 1 ELSE 0 END), 0) AS single_line_orders,
                    COALESCE(SUM(COALESCE(o.total_price, 0)), 0) AS monthly_revenue
                FROM paid_orders_30d po
                LEFT JOIN orders o ON o.store_id = %(store_id)s AND o.id = po.id
                LEFT JOIN order_line_stats ols ON ols.order_id = po.id
            ),
            store_aov_metric AS (
                SELECT COALESCE(AVG(COALESCE(o.total_price, 0)), 0) AS store_aov
                FROM orders o
                WHERE o.store_id = %(store_id)s
                  AND o.created_at >= NOW() - INTERVAL '90 days'
                  AND LOWER(COALESCE(o.financial_status, '')) IN ('paid', 'partially_refunded')
            )
            SELECT
                om.total_orders,
                om.avg_items_per_order,
                om.single_line_orders,
                om.monthly_revenue,
                COALESCE(sa.store_aov, 0) AS store_aov
            FROM order_metrics om
            CROSS JOIN store_aov_metric sa;
            """,
            {"store_id": store_id},
        )
        row = cursor.fetchone() or {}
    finally:
        if should_close:
            cursor.close()

    total_orders = int(row.get("total_orders") or 0)
    avg_items_per_order = float(row.get("avg_items_per_order") or 0.0)
    single_line_orders = int(row.get("single_line_orders") or 0)
    monthly_revenue = float(row.get("monthly_revenue") or 0.0)
    store_aov = float(row.get("store_aov") or 0.0)

    all_single_line = total_orders > 0 and single_line_orders == total_orders
    if not (total_orders >= 50 and avg_items_per_order < 1.5 and all_single_line):
        return {"detected": False}

    upsell_opportunity = monthly_revenue * 0.15
    daily_impact = upsell_opportunity / 30.0
    seven_day_projection = daily_impact * 7.0

    return {
        "action_type": ACTION_TYPE,
        "detected": True,
        "metrics": {
            "total_orders": total_orders,
            "avg_items_per_order": avg_items_per_order,
            "store_aov": store_aov,
            "monthly_revenue": monthly_revenue,
            "upsell_opportunity": upsell_opportunity,
        },
        "daily_impact": daily_impact,
        "total_value": upsell_opportunity,
        "seven_day_projection": seven_day_projection,
        "problem": (
            f"{total_orders} orders in 30 days average {avg_items_per_order:.1f} items — "
            "no post-purchase upsell pattern detected"
        ),
        "fix": (
            "Install a post-purchase upsell and raise free-shipping threshold "
            "above current AOV"
        ),
        "impact_bullets": [
            f"Estimated upsell opportunity: ${upsell_opportunity:,.2f}/month",
            "Single-item orders suggest customers leave after first purchase",
        ],
        "risk_bullets": [
            "Every month without upsells leaves recoverable revenue on the table",
            "Competitors capturing add-on revenue from the same traffic",
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
