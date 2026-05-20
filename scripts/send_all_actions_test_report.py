"""
One-off test: email a report containing every registered action type (not capped at 5).
Run from repo root: python scripts/send_all_actions_test_report.py [--store-id 1]

Does NOT modify production constants or schedule recurring sends.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from config.logging_config import setup_logging
from db.queries import get_store_display_name_by_id
from reporting.email_sender import send_email
from reporting.html_report import build_html_report
from scheduler.run_pipeline import REGISTERED_INSIGHT_ACTIONS

# Sample metrics so every advice_engine branch renders with real-looking numbers.
ALL_ACTION_TEST_METRICS: dict[str, dict] = {
    "dead_inventory": {
        "sku_count": 12,
        "total_units": 148,
        "days_stale": 127,
        "estimated_value": 4820.75,
        "store_aov": 64.50,
    },
    "high_return_rate": {
        "product_name": "CloudFlex Running Shoe",
        "return_rate": 0.42,
        "returned_units": 38,
        "revenue_lost": 3116.40,
        "store_aov": 58.0,
    },
    "churned_customers": {
        "churned_count": 460,
        "avg_days_since_order": 83.2,
        "store_aov": 58.0,
        "potential_recovery": 4002.0,
        "top_churned_product": "Daily Greens",
    },
    "low_repeat_purchase_rate": {
        "repeat_rate": 0.14,
        "total_customers": 4200,
        "one_time_buyers": 3612,
        "store_aov": 54.0,
        "revenue_if_10pct_improvement": 19504.80,
    },
    "high_value_customer_at_risk": {
        "customer_count": 27,
        "avg_ltv": 742.10,
        "days_since_last_order": 67.0,
        "total_ltv_at_risk": 20036.70,
        "store_aov": 61.0,
    },
    "abandoned_checkout_spike": {
        "abandoned_count": 318,
        "abandonment_rate": 0.79,
        "potential_revenue": 17490.0,
        "store_aov": 55.0,
        "prev_week_abandonment_rate": 0.68,
    },
    "low_margin_products": {
        "product_name": "Everyday Tee",
        "units_sold": 920,
        "estimated_margin": 0.17,
        "revenue_generated": 22080.0,
        "profit_generated": 3753.60,
        "store_avg_margin": 0.41,
    },
    "duplicate_orders": {
        "customer_id_display": "882104",
        "duplicate_order_entries": 2,
        "duplicate_charge_exposure": 129.00,
        "store_aov": 64.50,
    },
    "revenue_concentration": {
        "concentration_pct": 62.4,
        "top_two_revenue_share": 18420.00,
        "loyal_revenue_pool": 29550.00,
        "store_aov": 72.0,
    },
    "abnormal_discount": {
        "order_id_hint": "4509812",
        "discount_pct_hint": 72.5,
        "estimated_leak_usd": 890.00,
        "store_aov": 55.0,
    },
    "discount_overuse": {
        "discount_rate": 0.38,
        "discounted_orders": 142,
        "total_orders": 374,
        "total_discount_given": 2840.50,
        "avg_discount_amount": 19.99,
        "most_used_code": "SAVE15",
        "store_aov": 48.0,
    },
    "no_post_purchase_upsell": {
        "total_orders": 120,
        "avg_items_per_order": 1.1,
        "store_aov": 42.50,
        "monthly_revenue": 5100.0,
        "upsell_opportunity": 765.0,
    },
    "no_email_automation_flows": {
        "total_customers": 850,
        "one_time_buyers": 612,
        "repeat_rate": 0.22,
        "store_aov": 54.0,
        "winback_opportunity": 2643.84,
    },
    "low_aov_no_bundle_strategy": {
        "store_aov": 38.50,
        "total_orders": 85,
        "monthly_revenue": 3272.50,
        "bundle_opportunity": 654.50,
    },
    "single_product_revenue_concentration": {
        "top_product_name": "Hero Serum",
        "top_product_revenue_share": 0.68,
        "top_product_revenue": 22100.0,
        "total_revenue": 32500.0,
        "store_aov": 62.0,
    },
    "no_subscription_revenue": {
        "repeat_rate": 0.31,
        "total_repeat_orders": 48,
        "store_aov": 44.0,
        "monthly_revenue": 8800.0,
        "subscription_opportunity": 2200.0,
    },
    "high_single_order_customer_ratio": {
        "one_time_buyers": 420,
        "total_customers": 520,
        "one_time_ratio": 0.808,
        "store_aov": 51.0,
        "ltv_gap": 153.0,
        "actual_avg_ltv": 58.0,
    },
    "pricing_below_market": {
        "avg_product_price": 11.50,
        "low_price_revenue_share": 0.52,
        "store_aov": 28.00,
        "total_revenue": 4200.0,
        "price_increase_opportunity": 630.0,
    },
    "review_count_too_low": {
        "total_orders": 210,
        "store_aov": 46.0,
        "monthly_revenue": 9660.0,
        "review_opportunity": 1159.20,
    },
    "cart_abandonment_no_recovery": {
        "abandoned_count": 42,
        "abandonment_rate": 0.71,
        "store_aov": 55.0,
        "potential_recovery": 346.50,
        "weekly_loss": 2310.0,
    },
    "no_loyalty_program": {
        "repeat_rate": 0.28,
        "total_customers": 380,
        "repeat_buyers": 106,
        "store_aov": 49.0,
        "monthly_revenue": 7350.0,
        "loyalty_opportunity": 1323.0,
    },
}

ALL_ACTION_TEST_TARGETS: dict[str, list[dict]] = {
    "dead_inventory": [
        {"name": "Vintage Canvas Tote", "sku": "VCT-001", "inventory": 44, "sales_last_90d": 0},
    ],
    "high_return_rate": [
        {"name": "CloudFlex Running Shoe", "sku": "CF-42", "return_rate": 42.0, "returned_units": 38},
    ],
    "high_value_customer_at_risk": [
        {"name": "Alex M.", "email": "a***@example.com", "ltv": 842.10, "days_since_order": 67},
    ],
    "low_margin_products": [
        {"name": "Everyday Tee", "sku": "TEE-BLK", "price": 18.0, "units_sold": 920},
    ],
    "revenue_concentration": [
        {"name": "Jordan K.", "total_spent": 12400.0, "orders_count": 18},
    ],
    "single_product_revenue_concentration": [
        {"name": "Hero Serum", "sku": "HS-100"},
    ],
    "discount_overuse": [
        {"name": "SAVE15", "code": "SAVE15", "usage_count": 142, "total_discounted": 2840.50},
    ],
}


def _build_test_report_data(*, store_id: int) -> dict:
    store_name = get_store_display_name_by_id(store_id) or f"Store {store_id}"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    actions: list[dict] = []
    total_daily = 0.0
    total_value = 0.0

    for idx, action_type in enumerate(REGISTERED_INSIGHT_ACTIONS, start=1):
        metrics = dict(ALL_ACTION_TEST_METRICS.get(action_type) or {"store_aov": 35.0})
        raw_value = (
            metrics.get("estimated_value")
            or metrics.get("potential_recovery")
            or metrics.get("weekly_loss")
            or metrics.get("total_ltv_at_risk")
            or metrics.get("upsell_opportunity")
            or metrics.get("winback_opportunity")
            or metrics.get("revenue_if_10pct_improvement")
            or metrics.get("potential_revenue")
            or metrics.get("abandoned_value")
            or metrics.get("monthly_revenue")
            or metrics.get("discount_amount")
            or metrics.get("revenue_at_risk")
            or metrics.get("lifetime_value")
            or metrics.get("revenue_lost")
            or metrics.get("profit_generated")
            or metrics.get("revenue_generated")
            or metrics.get("duplicate_charge_exposure")
            or metrics.get("loyal_revenue_pool")
            or metrics.get("estimated_leak_usd")
            or metrics.get("total_discount_given")
            or metrics.get("top_product_revenue")
            or metrics.get("ltv_gap")
            or metrics.get("price_increase_opportunity")
            or 120.0
        )
        daily = round(float(raw_value) / 30.0, 2)
        weekly = round(daily * 7.0, 2)
        total_daily += daily
        total_value += weekly
        actions.append(
            {
                "number": idx,
                "type": "PRIMARY REVENUE LEAK" if idx == 1 else "SECONDARY OPTIMIZATION LEAK",
                "daily_impact": daily,
                "problem": f"[TEST] Preview of {action_type.replace('_', ' ')} advice block.",
                "fix": f"[TEST] Execute playbook for {action_type}.",
                "impact_bullets": [f"Recover ${weekly:,.2f} over 7 days (test data)"],
                "risk_bullets": ["Test report — not live signal data"],
                "targets": list(ALL_ACTION_TEST_TARGETS.get(action_type) or []),
                "state": "PENDING",
                "action_type": action_type,
                "metrics": metrics,
            }
        )

    return {
        "store_name": store_name,
        "date": today,
        "status": "warning",
        "daily_impact": round(total_daily, 2),
        "total_value": round(total_value, 2),
        "seven_day_projection": round(total_value * 0.45, 2),
        "root_cause": "TEST REPORT — ALL ACTION TYPES",
        "execute_value": round(total_value * 0.55, 2),
        "ignore_loss": round(total_value * 0.45, 2),
        "delta": round(total_value * 0.10, 2),
        "actions": actions,
    }


def main() -> int:
    setup_logging()
    parser = argparse.ArgumentParser(description="Send one test email with all action types.")
    parser.add_argument("--store-id", type=int, default=1, help="Store id (default: 1)")
    args = parser.parse_args()
    store_id = int(args.store_id)

    report_data = _build_test_report_data(store_id=store_id)
    n = len(report_data["actions"])
    print(f"Built test report with {n} actions for store_id={store_id}.")

    from db.queries import get_store_contact_email_by_id

    recipient = get_store_contact_email_by_id(store_id)
    if not recipient:
        raise RuntimeError(f"No contact_email for store_id={store_id}")

    subject = f"[TEST — ALL {n} ACTIONS] Preview report — not live signals"
    html_content = build_html_report(report_data)
    store_label = str(report_data.get("store_name") or f"Store {store_id}")
    plain_body = (
        f"{store_label} — ONE-TIME TEST REPORT\n"
        f"Contains all {n} registered action types for copy/advice verification.\n"
        f"Date: {report_data.get('date')}\n"
        "This is not generated from live pipeline ranking.\n"
    )
    send_email(subject, plain_body, html_body=html_content, recipient=recipient)
    print(f"Sent to {recipient} ({n} action cards).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
