from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor


ACTION_TYPE = "discount_overuse"


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


def _discount_code_lateral_sql(column: dict | None) -> str | None:
    if not column:
        return None

    data_type = column["data_type"]
    if data_type in {"json", "jsonb"}:
        return """
            SELECT COALESCE(
                NULLIF(TRIM(elem->>'code'), ''),
                NULLIF(TRIM(elem->>'title'), ''),
                NULLIF(TRIM(BOTH '"' FROM elem::text), ''),
                'UNKNOWN'
            ) AS code
            FROM jsonb_array_elements(
                CASE
                    WHEN jsonb_typeof(o.discount_codes::jsonb) = 'array'
                        THEN o.discount_codes::jsonb
                    WHEN jsonb_typeof(o.discount_codes::jsonb) = 'string'
                        THEN jsonb_build_array(o.discount_codes::jsonb)
                    ELSE '[]'::jsonb
                END
            ) AS elem
        """
    if data_type == "array":
        return """
            SELECT COALESCE(NULLIF(TRIM(code_val), ''), 'UNKNOWN') AS code
            FROM unnest(o.discount_codes::text[]) AS code_val
        """
    return """
        SELECT COALESCE(NULLIF(TRIM(o.discount_codes::text), ''), 'UNKNOWN') AS code
    """


def run_insight(db: Any, *, store_id: int) -> dict:
    cursor, should_close = _get_cursor(db)
    try:
        discount_codes_column = _load_discount_codes_column(cursor)
        discounted_predicate = _discounted_order_predicate(discount_codes_column)

        cursor.execute(
            f"""
            WITH paid_orders AS (
                SELECT
                    o.id,
                    COALESCE(o.total_discounts, 0) AS discount_amount,
                    ({discounted_predicate}) AS is_discounted
                FROM orders o
                WHERE o.store_id = %(store_id)s
                  AND o.created_at >= NOW() - INTERVAL '30 days'
                  AND LOWER(COALESCE(o.financial_status, '')) IN ('paid', 'partially_refunded')
            ),
            order_metrics AS (
                SELECT
                    COALESCE(COUNT(*), 0) AS total_orders,
                    COALESCE(COUNT(*) FILTER (WHERE is_discounted), 0) AS discounted_orders,
                    COALESCE(AVG(discount_amount) FILTER (WHERE is_discounted), 0) AS avg_discount_amount,
                    COALESCE(SUM(discount_amount) FILTER (WHERE is_discounted), 0) AS total_discount_given
                FROM paid_orders
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
                om.discounted_orders,
                om.avg_discount_amount,
                om.total_discount_given,
                COALESCE(sa.store_aov, 0) AS store_aov
            FROM order_metrics om
            CROSS JOIN store_aov_metric sa;
            """,
            {"store_id": store_id},
        )
        row = cursor.fetchone() or {}

        most_used_code = ""
        top_target: dict | None = None
        code_lateral = _discount_code_lateral_sql(discount_codes_column)
        if code_lateral:
            cursor.execute(
                f"""
                WITH paid_discounted AS (
                    SELECT
                        o.id,
                        COALESCE(o.total_discounts, 0) AS discount_amount,
                        codes.code
                    FROM orders o
                    CROSS JOIN LATERAL (
                        {code_lateral}
                    ) AS codes
                    WHERE o.store_id = %(store_id)s
                      AND o.created_at >= NOW() - INTERVAL '30 days'
                      AND LOWER(COALESCE(o.financial_status, '')) IN ('paid', 'partially_refunded')
                      AND ({discounted_predicate})
                ),
                code_stats AS (
                    SELECT
                        code,
                        COUNT(*)::int AS usage_count,
                        COALESCE(SUM(discount_amount), 0) AS total_discounted
                    FROM paid_discounted
                    GROUP BY code
                )
                SELECT code, usage_count, total_discounted
                FROM code_stats
                ORDER BY usage_count DESC, total_discounted DESC
                LIMIT 1;
                """,
                {"store_id": store_id},
            )
            code_row = cursor.fetchone() or {}
            most_used_code = str(code_row.get("code") or "").strip()
            if most_used_code:
                top_target = {
                    "code": most_used_code,
                    "usage_count": int(code_row.get("usage_count") or 0),
                    "total_discounted": float(code_row.get("total_discounted") or 0.0),
                }
    finally:
        if should_close:
            cursor.close()

    total_orders = int(row.get("total_orders") or 0)
    discounted_orders = int(row.get("discounted_orders") or 0)
    total_discount_given = float(row.get("total_discount_given") or 0.0)
    avg_discount_amount = float(row.get("avg_discount_amount") or 0.0)
    store_aov = float(row.get("store_aov") or 0.0)
    discount_rate = (discounted_orders / total_orders) if total_orders > 0 else 0.0

    if not (discount_rate > 0.30 and total_orders >= 10):
        return {"detected": False}

    if not most_used_code:
        most_used_code = "STORE_DISCOUNT"
    if top_target is None:
        top_target = {
            "code": most_used_code,
            "usage_count": discounted_orders,
            "total_discounted": total_discount_given,
        }

    daily_impact = (total_discount_given / 30.0) * 0.40
    total_value = total_discount_given * 0.40
    seven_day_projection = daily_impact * 7.0

    return {
        "action_type": ACTION_TYPE,
        "detected": True,
        "discount_rate": discount_rate,
        "discounted_orders": discounted_orders,
        "total_orders": total_orders,
        "total_discount_given": total_discount_given,
        "avg_discount_amount": avg_discount_amount,
        "most_used_code": most_used_code,
        "store_aov": store_aov,
        "daily_impact": daily_impact,
        "total_value": total_value,
        "seven_day_projection": seven_day_projection,
        "problem": (
            f"{discount_rate * 100:.1f}% of your orders in the last "
            f"30 days used a discount code — you gave away "
            f"${total_discount_given:.2f} in discounts this month"
        ),
        "fix": (
            "Replace blanket discount codes with value-based offers "
            "— free shipping, bundles, or loyalty rewards"
        ),
        "impact_bullets": [
            f"→ Recover ${total_discount_given * 0.40:.2f} in monthly "
            "margin by reducing discount dependency by 40%",
            "→ Customers who pay full price have 3x higher LTV than "
            "discount-driven buyers",
        ],
        "risk_bullets": [
            f"⚠ At current rate you will give away "
            f"${total_discount_given * 12:.2f} in discounts this year",
            f"⚠ {discount_rate * 100:.1f}% of your customers now "
            "expect a discount before buying — this gets worse "
            "every month you wait",
        ],
        "targets": [top_target],
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
