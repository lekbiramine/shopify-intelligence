from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor


ACTION_TYPE = "no_loyalty_program"


def _get_cursor(db: Any):
    if hasattr(db, "execute"):
        return db, False
    if hasattr(db, "cursor"):
        return db.cursor(cursor_factory=RealDictCursor), True
    raise TypeError("db must be a DB cursor or psycopg2 connection")


def _load_discount_codes_column(cursor: Any) -> dict | None:
    cursor.execute(
        """
        SELECT data_type, udt_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'orders'
          AND column_name = 'discount_codes'
        LIMIT 1;
        """
    )
    row = cursor.fetchone()
    if not row:
        return None
    data_type = str(row.get("data_type") or row.get("udt_name") or "").lower()
    return {"data_type": data_type}


def _discounted_order_predicate(column: dict | None) -> str:
    if not column:
        return "COALESCE(o.total_discounts, 0) > 0"
    data_type = column["data_type"]
    if data_type in {"json", "jsonb"}:
        return """
            o.discount_codes IS NOT NULL
            AND (
                (
                    jsonb_typeof(o.discount_codes::jsonb) = 'array'
                    AND jsonb_array_length(o.discount_codes::jsonb) > 0
                )
                OR (
                    jsonb_typeof(o.discount_codes::jsonb) = 'string'
                    AND NULLIF(TRIM(BOTH '"' FROM o.discount_codes::text), '') IS NOT NULL
                )
            )
        """
    if data_type == "array":
        return """
            o.discount_codes IS NOT NULL
            AND COALESCE(array_length(o.discount_codes::text[], 1), 0) > 0
        """
    return """
        o.discount_codes IS NOT NULL
        AND NULLIF(TRIM(o.discount_codes::text), '') IS NOT NULL
        AND TRIM(o.discount_codes::text) NOT IN ('[]', 'null', '{}', '""')
    """


def run_insight(db: Any, *, store_id: int) -> dict:
    cursor, should_close = _get_cursor(db)
    try:
        discount_codes_column = _load_discount_codes_column(cursor)
        discounted_predicate = _discounted_order_predicate(discount_codes_column)

        cursor.execute(
            f"""
            WITH order_flags AS (
                SELECT
                    o.customer_id,
                    o.created_at,
                    ({discounted_predicate}) AS is_discounted
                FROM orders o
                WHERE o.store_id = %(store_id)s
                  AND o.customer_id IS NOT NULL
                  AND LOWER(COALESCE(o.financial_status, '')) IN ('paid', 'partially_refunded')
            ),
            customer_orders AS (
                SELECT
                    customer_id,
                    COUNT(*) AS order_count,
                    COALESCE(
                        SUM(CASE WHEN is_discounted THEN 1 ELSE 0 END)
                            FILTER (WHERE order_seq >= 2),
                        0
                    ) AS discounted_repeat_orders
                FROM (
                    SELECT
                        customer_id,
                        is_discounted,
                        ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY created_at) AS order_seq
                    FROM order_flags
                ) ranked
                GROUP BY customer_id
            ),
            repeat_buyer_discounts AS (
                SELECT
                    COALESCE(COUNT(*) FILTER (WHERE order_count >= 2), 0) AS repeat_buyers,
                    COALESCE(
                        SUM(discounted_repeat_orders) FILTER (WHERE order_count >= 2),
                        0
                    ) AS repeat_orders_with_discount
                FROM customer_orders
            ),
            customer_stats AS (
                SELECT
                    COALESCE(COUNT(DISTINCT customer_id), 0) AS total_customers,
                    COALESCE(COUNT(DISTINCT CASE WHEN order_count >= 2 THEN customer_id END), 0) AS repeat_customer_count
                FROM (
                    SELECT customer_id, COUNT(*) AS order_count
                    FROM customer_orders
                    GROUP BY customer_id
                ) c
            ),
            order_volume AS (
                SELECT COALESCE(COUNT(*), 0) AS total_orders
                FROM orders o
                WHERE o.store_id = %(store_id)s
                  AND o.created_at >= NOW() - INTERVAL '30 days'
                  AND LOWER(COALESCE(o.financial_status, '')) IN ('paid', 'partially_refunded')
            ),
            revenue_30d AS (
                SELECT COALESCE(SUM(COALESCE(o.total_price, 0)), 0) AS monthly_revenue
                FROM orders o
                WHERE o.store_id = %(store_id)s
                  AND o.created_at >= NOW() - INTERVAL '30 days'
                  AND LOWER(COALESCE(o.financial_status, '')) IN ('paid', 'partially_refunded')
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
                cs.repeat_customer_count AS repeat_buyers,
                rbd.repeat_orders_with_discount,
                ov.total_orders,
                COALESCE(rv.monthly_revenue, 0) AS monthly_revenue,
                COALESCE(sa.store_aov, 0) AS store_aov
            FROM customer_stats cs
            CROSS JOIN repeat_buyer_discounts rbd
            CROSS JOIN order_volume ov
            CROSS JOIN revenue_30d rv
            CROSS JOIN store_aov_metric sa;
            """,
            {"store_id": store_id},
        )
        row = cursor.fetchone() or {}
    finally:
        if should_close:
            cursor.close()

    total_customers = int(row.get("total_customers") or 0)
    repeat_buyers = int(row.get("repeat_buyers") or 0)
    repeat_orders_with_discount = int(row.get("repeat_orders_with_discount") or 0)
    total_orders = int(row.get("total_orders") or 0)
    monthly_revenue = float(row.get("monthly_revenue") or 0.0)
    store_aov = float(row.get("store_aov") or 0.0)
    repeat_rate = (repeat_buyers / total_customers) if total_customers > 0 else 0.0

    repeat_discount_share = (
        (repeat_orders_with_discount / max(repeat_buyers, 1)) if repeat_buyers > 0 else 0.0
    )
    has_loyalty_discount_pattern = repeat_buyers > 0 and repeat_discount_share >= 0.15

    if not (
        repeat_rate > 0.20
        and total_orders >= 30
        and not has_loyalty_discount_pattern
    ):
        return {"detected": False}

    loyalty_opportunity = monthly_revenue * 0.18
    daily_impact = loyalty_opportunity / 30.0
    seven_day_projection = daily_impact * 7.0

    return {
        "action_type": ACTION_TYPE,
        "detected": True,
        "metrics": {
            "repeat_rate": repeat_rate,
            "total_customers": total_customers,
            "repeat_buyers": repeat_buyers,
            "store_aov": store_aov,
            "monthly_revenue": monthly_revenue,
            "loyalty_opportunity": loyalty_opportunity,
        },
        "daily_impact": daily_impact,
        "total_value": loyalty_opportunity,
        "seven_day_projection": seven_day_projection,
        "problem": (
            f"{repeat_rate * 100:.1f}% repeat rate with {repeat_buyers} repeat buyers — "
            "no loyalty discount pattern on 2nd+ orders"
        ),
        "fix": (
            "Launch buy-5-get-20%-off loyalty mechanic and VIP tier for top repeat buyers"
        ),
        "impact_bullets": [
            f"Loyalty revenue opportunity: ${loyalty_opportunity:,.2f}/month",
            f"{repeat_buyers} repeat buyers with no structured reward",
        ],
        "risk_bullets": [
            "Repeat buyers can leave for a competitor offer",
            "Habit without commitment is fragile retention",
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
