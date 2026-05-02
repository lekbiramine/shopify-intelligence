from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor


ACTION_TYPE = "high_value_customer_at_risk"


def _get_cursor(db: Any):
    if hasattr(db, "execute"):
        return db, False
    if hasattr(db, "cursor"):
        return db.cursor(cursor_factory=RealDictCursor), True
    raise TypeError("db must be a DB cursor or psycopg2 connection")


def _mask_email(email: str) -> str:
    text = (email or "").strip()
    if "@" not in text:
        return ""
    local, domain = text.split("@", 1)
    if not local:
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"


def run_insight(db: Any) -> dict:
    cursor, should_close = _get_cursor(db)
    try:
        cursor.execute(
            """
            WITH customer_ltv AS (
                SELECT
                    c.id AS customer_id,
                    COALESCE(NULLIF(TRIM(CONCAT(COALESCE(c.first_name, ''), ' ', COALESCE(c.last_name, ''))), ''), 'Customer') AS name,
                    COALESCE(c.email, '') AS email,
                    COALESCE(SUM(COALESCE(o.total_price, 0)), 0) AS lifetime_spend,
                    MAX(o.created_at) AS last_order_date
                FROM customers c
                LEFT JOIN orders o
                    ON o.store_id = c.store_id
                   AND o.customer_id = c.id
                   AND COALESCE(o.financial_status, '') NOT IN ('voided', 'cancelled')
                GROUP BY c.id, c.first_name, c.last_name, c.email
            ),
            ranked AS (
                SELECT
                    customer_id,
                    name,
                    email,
                    lifetime_spend,
                    last_order_date,
                    NTILE(5) OVER (ORDER BY lifetime_spend DESC) AS spend_quintile
                FROM customer_ltv
                WHERE lifetime_spend > 0
                  AND last_order_date IS NOT NULL
            ),
            at_risk_vips AS (
                SELECT
                    customer_id,
                    name,
                    email,
                    lifetime_spend,
                    EXTRACT(EPOCH FROM (NOW() - last_order_date)) / 86400.0 AS days_since_order
                FROM ranked
                WHERE spend_quintile = 1
                  AND EXTRACT(EPOCH FROM (NOW() - last_order_date)) / 86400.0 BETWEEN 45 AND 90
            ),
            store_aov AS (
                SELECT COALESCE(AVG(COALESCE(total_price, 0)), 0) AS value
                FROM orders
                WHERE COALESCE(financial_status, '') NOT IN ('voided', 'cancelled')
            )
            SELECT
                COALESCE(COUNT(*), 0) AS customer_count,
                COALESCE(AVG(COALESCE(a.lifetime_spend, 0)), 0) AS avg_ltv,
                COALESCE(AVG(COALESCE(a.days_since_order, 0)), 0) AS days_since_last_order,
                COALESCE((SELECT value FROM store_aov), 0) AS store_aov
            FROM at_risk_vips a;
            """
        )
        summary = cursor.fetchone() or {}

        cursor.execute(
            """
            WITH customer_ltv AS (
                SELECT
                    c.id AS customer_id,
                    COALESCE(NULLIF(TRIM(CONCAT(COALESCE(c.first_name, ''), ' ', COALESCE(c.last_name, ''))), ''), 'Customer') AS name,
                    COALESCE(c.email, '') AS email,
                    COALESCE(SUM(COALESCE(o.total_price, 0)), 0) AS lifetime_spend,
                    MAX(o.created_at) AS last_order_date
                FROM customers c
                LEFT JOIN orders o
                    ON o.store_id = c.store_id
                   AND o.customer_id = c.id
                   AND COALESCE(o.financial_status, '') NOT IN ('voided', 'cancelled')
                GROUP BY c.id, c.first_name, c.last_name, c.email
            ),
            ranked AS (
                SELECT
                    customer_id,
                    name,
                    email,
                    lifetime_spend,
                    last_order_date,
                    NTILE(5) OVER (ORDER BY lifetime_spend DESC) AS spend_quintile
                FROM customer_ltv
                WHERE lifetime_spend > 0
                  AND last_order_date IS NOT NULL
            )
            SELECT
                name,
                email,
                lifetime_spend AS ltv,
                CAST(EXTRACT(EPOCH FROM (NOW() - last_order_date)) / 86400.0 AS INT) AS days_since_order
            FROM ranked
            WHERE spend_quintile = 1
              AND EXTRACT(EPOCH FROM (NOW() - last_order_date)) / 86400.0 BETWEEN 45 AND 90
            ORDER BY lifetime_spend DESC
            LIMIT 5;
            """
        )
        raw_targets = cursor.fetchall() or []
    finally:
        if should_close:
            cursor.close()

    customer_count = int(summary.get("customer_count") or 0)
    if customer_count < 2:
        return {"detected": False}

    avg_ltv = float(summary.get("avg_ltv") or 0.0)
    days_since_last_order = float(summary.get("days_since_last_order") or 0.0)
    store_aov = float(summary.get("store_aov") or 0.0)
    total_ltv_at_risk = customer_count * avg_ltv
    daily_impact = (total_ltv_at_risk * 0.30) / 90.0
    seven_day_projection = daily_impact * 7.0

    targets = [
        {
            "name": str(t.get("name") or "Customer"),
            "email": _mask_email(str(t.get("email") or "")),
            "ltv": float(t.get("ltv") or 0.0),
            "days_since_order": int(t.get("days_since_order") or 0),
        }
        for t in raw_targets
    ]

    return {
        "action_type": ACTION_TYPE,
        "detected": True,
        "metrics": {
            "customer_count": customer_count,
            "avg_ltv": avg_ltv,
            "days_since_last_order": days_since_last_order,
            "total_ltv_at_risk": total_ltv_at_risk,
            "store_aov": store_aov,
        },
        "daily_impact": daily_impact,
        "total_value": total_ltv_at_risk,
        "seven_day_projection": seven_day_projection,
        "problem": (
            f"{customer_count} high-value customers are going quiet — "
            f"last order {days_since_last_order:.0f} days ago on average"
        ),
        "fix": (
            "Send a personal email from the store owner account to "
            "each VIP customer with an exclusive offer"
        ),
        "impact_bullets": [
            f"${total_ltv_at_risk:,.2f} of historical customer value is at early churn risk",
            "Retention interventions on VIP segments usually outperform broad campaigns",
        ],
        "risk_bullets": [
            "VIP churn compounds because replacement CAC is higher than retention cost",
            "Waiting past 90 days sharply lowers reactivation probability",
        ],
        "targets": targets,
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
