from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor


ACTION_TYPE = "single_product_revenue_concentration"


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
            WITH product_revenue AS (
                SELECT
                    oi.product_id,
                    COALESCE(p.title, 'Unknown product') AS product_name,
                    COALESCE(SUM(COALESCE(oi.quantity, 0) * COALESCE(oi.price, 0)), 0) AS revenue
                FROM order_items oi
                JOIN orders o ON o.store_id = oi.store_id AND o.id = oi.order_id
                LEFT JOIN products p ON p.store_id = oi.store_id AND p.id = oi.product_id
                WHERE oi.store_id = %(store_id)s
                  AND o.created_at >= NOW() - INTERVAL '90 days'
                  AND LOWER(COALESCE(o.financial_status, '')) IN ('paid', 'partially_refunded')
                GROUP BY oi.product_id, p.title
                HAVING COALESCE(SUM(COALESCE(oi.quantity, 0) * COALESCE(oi.price, 0)), 0) > 0
            ),
            totals AS (
                SELECT
                    COALESCE(SUM(revenue), 0) AS total_revenue,
                    COALESCE(COUNT(*), 0) AS products_with_sales
                FROM product_revenue
            ),
            top_product AS (
                SELECT product_name, revenue
                FROM product_revenue
                ORDER BY revenue DESC
                LIMIT 1
            ),
            store_aov_metric AS (
                SELECT COALESCE(AVG(COALESCE(o.total_price, 0)), 0) AS store_aov
                FROM orders o
                WHERE o.store_id = %(store_id)s
                  AND o.created_at >= NOW() - INTERVAL '90 days'
                  AND LOWER(COALESCE(o.financial_status, '')) IN ('paid', 'partially_refunded')
            )
            SELECT
                tp.product_name AS top_product_name,
                COALESCE(tp.revenue, 0) AS top_product_revenue,
                COALESCE(t.total_revenue, 0) AS total_revenue,
                COALESCE(t.products_with_sales, 0) AS products_with_sales,
                COALESCE(sa.store_aov, 0) AS store_aov
            FROM totals t
            LEFT JOIN top_product tp ON TRUE
            CROSS JOIN store_aov_metric sa;
            """,
            {"store_id": store_id},
        )
        row = cursor.fetchone() or {}
    finally:
        if should_close:
            cursor.close()

    top_product_name = str(row.get("top_product_name") or "Top product")
    top_product_revenue = float(row.get("top_product_revenue") or 0.0)
    total_revenue = float(row.get("total_revenue") or 0.0)
    products_with_sales = int(row.get("products_with_sales") or 0)
    store_aov = float(row.get("store_aov") or 0.0)
    top_product_revenue_share = (
        (top_product_revenue / total_revenue) if total_revenue > 0 else 0.0
    )

    if not (products_with_sales >= 3 and top_product_revenue_share > 0.60):
        return {"detected": False}

    daily_impact = (top_product_revenue * 0.10) / 30.0
    seven_day_projection = daily_impact * 7.0

    return {
        "action_type": ACTION_TYPE,
        "detected": True,
        "metrics": {
            "top_product_name": top_product_name,
            "top_product_revenue_share": top_product_revenue_share,
            "top_product_revenue": top_product_revenue,
            "total_revenue": total_revenue,
            "store_aov": store_aov,
            "products_with_sales": products_with_sales,
        },
        "daily_impact": daily_impact,
        "total_value": top_product_revenue * 0.10,
        "seven_day_projection": seven_day_projection,
        "problem": (
            f"{top_product_name} drives {top_product_revenue_share * 100:.1f}% of revenue — "
            "dangerous single-product concentration"
        ),
        "fix": (
            "Run campaigns and bundles to grow #2 and #3 products this month"
        ),
        "impact_bullets": [
            f"${top_product_revenue:,.2f} from one SKU of ${total_revenue:,.2f} total",
            f"{products_with_sales} products with sales — diversification needed",
        ],
        "risk_bullets": [
            "One product failure can collapse monthly revenue",
            "Supply, reviews, or ads on one SKU affect the whole business",
        ],
        "targets": [{"name": top_product_name, "sku": "TOP_SKU"}],
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
