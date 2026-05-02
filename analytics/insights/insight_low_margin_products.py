from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor


ACTION_TYPE = "low_margin_products"
ESTIMATED_COGS_RATIO = 0.40
ESTIMATED_MARGIN = 1.0 - ESTIMATED_COGS_RATIO


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
            WITH active_products AS (
                SELECT
                    p.id AS product_id,
                    COALESCE(p.title, 'Unknown product') AS product_name,
                    COALESCE(p.status, 'active') AS status
                FROM products p
                WHERE COALESCE(p.status, 'active') = 'active'
            ),
            product_prices AS (
                SELECT
                    ap.product_id,
                    ap.product_name,
                    COALESCE(v.sku, '') AS sku,
                    COALESCE(AVG(COALESCE(v.price, 0)), 0) AS avg_price
                FROM active_products ap
                LEFT JOIN variants v ON v.product_id = ap.product_id
                GROUP BY ap.product_id, ap.product_name, v.sku
            ),
            sales_90d AS (
                SELECT
                    oi.product_id,
                    COALESCE(SUM(COALESCE(oi.quantity, 0)), 0) AS units_sold
                FROM order_items oi
                LEFT JOIN orders o ON o.id = oi.order_id
                WHERE o.created_at >= NOW() - INTERVAL '90 days'
                  AND COALESCE(o.financial_status, '') NOT IN ('voided', 'cancelled')
                GROUP BY oi.product_id
            ),
            store_price_stats AS (
                SELECT
                    COALESCE(AVG(COALESCE(v.price, 0)), 0) AS avg_store_price
                FROM variants v
                LEFT JOIN products p ON p.id = v.product_id
                WHERE COALESCE(p.status, 'active') = 'active'
            ),
            flagged AS (
                SELECT
                    pp.product_id,
                    pp.product_name,
                    pp.sku,
                    COALESCE(pp.avg_price, 0) AS price,
                    COALESCE(s.units_sold, 0) AS units_sold,
                    COALESCE(st.avg_store_price, 0) AS avg_store_price
                FROM product_prices pp
                LEFT JOIN sales_90d s ON s.product_id = pp.product_id
                CROSS JOIN store_price_stats st
                WHERE COALESCE(pp.avg_price, 0) < (0.6 * COALESCE(st.avg_store_price, 0))
                  AND COALESCE(s.units_sold, 0) >= 5
            )
            SELECT
                f.product_name,
                f.sku,
                f.price,
                f.units_sold,
                f.avg_store_price,
                (COALESCE(f.units_sold, 0) * COALESCE(f.price, 0)) AS revenue_generated
            FROM flagged f
            ORDER BY f.units_sold DESC, f.price ASC
            LIMIT 1;
            """
        )
        flagged = cursor.fetchone() or {}
    finally:
        if should_close:
            cursor.close()

    if not flagged:
        return {"detected": False}

    product_name = str(flagged.get("product_name") or "Unknown product")
    sku = str(flagged.get("sku") or "")
    price = float(flagged.get("price") or 0.0)
    units_sold = int(flagged.get("units_sold") or 0)
    if units_sold <= 0:
        return {"detected": False}
    revenue_generated = float(flagged.get("revenue_generated") or 0.0)
    profit_generated = revenue_generated * ESTIMATED_MARGIN
    daily_impact = (revenue_generated * 0.15) / 90.0
    seven_day_projection = daily_impact * 7.0

    # True margin requires merchant-provided COGS data per SKU.
    # Future dashboard feature: allow merchants to input actual COGS for precise margin analysis.
    return {
        "action_type": ACTION_TYPE,
        "detected": True,
        "metrics": {
            "product_name": product_name,
            "units_sold": units_sold,
            "estimated_margin": ESTIMATED_MARGIN,
            "revenue_generated": revenue_generated,
            "profit_generated": profit_generated,
            "store_avg_margin": ESTIMATED_MARGIN,
        },
        "daily_impact": daily_impact,
        "total_value": profit_generated,
        "seven_day_projection": seven_day_projection,
        "problem": (
            f"{product_name} sells well but at a price that may be "
            "compressing your margins"
        ),
        "fix": (
            "Test a 15% price increase on this product and monitor "
            "conversion rate for 14 days"
        ),
        "impact_bullets": [
            f"{units_sold} units sold in 90 days at ${price:,.2f} average price",
            "Pricing optimization can improve blended margin without adding fulfillment complexity",
        ],
        "risk_bullets": [
            "High-volume low-price SKUs can hide poor contribution margin",
            "Scale on low-margin products can reduce overall cash generation",
        ],
        "targets": [
            {"name": product_name, "sku": sku, "price": price, "units_sold": units_sold}
        ],
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
