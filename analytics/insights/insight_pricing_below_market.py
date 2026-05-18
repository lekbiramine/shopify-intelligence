from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor


ACTION_TYPE = "pricing_below_market"


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
            line_revenue AS (
                SELECT
                    COALESCE(oi.price, 0) AS unit_price,
                    COALESCE(oi.quantity, 0) * COALESCE(oi.price, 0) AS line_revenue
                FROM order_items oi
                INNER JOIN paid_orders_30d po ON po.id = oi.order_id
                WHERE oi.store_id = %(store_id)s
            ),
            revenue_stats AS (
                SELECT
                    COALESCE(SUM(line_revenue), 0) AS total_revenue,
                    COALESCE(SUM(CASE WHEN unit_price < 15 THEN line_revenue ELSE 0 END), 0) AS low_price_revenue,
                    COALESCE(AVG(NULLIF(unit_price, 0)), 0) AS avg_product_price
                FROM line_revenue
            ),
            order_stats AS (
                SELECT
                    COALESCE(COUNT(*), 0) AS total_orders,
                    COALESCE(AVG(total_price), 0) AS store_aov
                FROM paid_orders_30d
            )
            SELECT
                rs.total_revenue,
                rs.low_price_revenue,
                rs.avg_product_price,
                os.total_orders,
                os.store_aov
            FROM revenue_stats rs
            CROSS JOIN order_stats os;
            """,
            {"store_id": store_id},
        )
        row = cursor.fetchone() or {}
    finally:
        if should_close:
            cursor.close()

    total_revenue = float(row.get("total_revenue") or 0.0)
    low_price_revenue = float(row.get("low_price_revenue") or 0.0)
    avg_product_price = float(row.get("avg_product_price") or 0.0)
    total_orders = int(row.get("total_orders") or 0)
    store_aov = float(row.get("store_aov") or 0.0)
    low_price_revenue_share = (low_price_revenue / total_revenue) if total_revenue > 0 else 0.0

    if not (
        store_aov < 35.0
        and total_orders >= 15
        and low_price_revenue_share > 0.40
    ):
        return {"detected": False}

    price_increase_opportunity = total_revenue * 0.15
    daily_impact = price_increase_opportunity / 30.0
    seven_day_projection = daily_impact * 7.0

    return {
        "action_type": ACTION_TYPE,
        "detected": True,
        "metrics": {
            "avg_product_price": avg_product_price,
            "low_price_revenue_share": low_price_revenue_share,
            "store_aov": store_aov,
            "total_revenue": total_revenue,
            "price_increase_opportunity": price_increase_opportunity,
        },
        "daily_impact": daily_impact,
        "total_value": price_increase_opportunity,
        "seven_day_projection": seven_day_projection,
        "problem": (
            f"Avg product price ${avg_product_price:.2f} — "
            f"{low_price_revenue_share * 100:.1f}% of revenue from items under $15"
        ),
        "fix": (
            "Test 10% price increase on #1 seller and bundle low-price SKUs"
        ),
        "impact_bullets": [
            f"15% price lift opportunity: ${price_increase_opportunity:,.2f}/month",
            f"AOV ${store_aov:.2f} signals undercharging",
        ],
        "risk_bullets": [
            "Low prices attract price-sensitive buyers who churn easily",
            "Margin compression limits ad spend and growth",
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
