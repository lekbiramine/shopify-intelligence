from reporting.pdf_report_v2 import (
    _action_priority_metrics,
    _dead_inventory_items,
    build_structured_actions,
    compute_store_decision_financials,
    projected_7d_loss,
    recoverable_opportunity,
)


def test_decision_execute_and_ignore_are_distinct():
    summary = {
        "insights": [
            {
                "title": "Dead Inventory",
                "severity": "medium",
                "potential_value": 1000.0,
                "impact_type": "recoverable",
                "loss_window_days": 7,
                "routing_type": "dead_inventory",
                "problem": "2 SKUs never sold.",
                "action": "Discount and bundle.",
                "exact_items": ["Widget — SKU A1 — inventory 5 — 90d sales 0 — est. value $500.00"],
            }
        ],
        "anomalies": {
            "no_sales_products": [
                {
                    "product_title": "Widget",
                    "primary_sku": "A1",
                    "total_available": 5,
                    "est_on_hand_value": 500.0,
                }
            ]
        },
        "inventory": {"low_stock": [], "critical_stock": [], "out_of_stock": []},
        "customers": {"churned": [], "loyal": []},
        "revenue": {"high_return_rate": [], "trend": {}},
    }
    fin = compute_store_decision_financials(summary)
    assert fin["execute_value"] == 1000.0
    assert fin["ignore_value"] == 450.0
    assert fin["net_delta"] == 550.0
    assert fin["execute_value"] > fin["ignore_value"]


def test_action_priority_prefers_explicit_daily_impact():
    item = {"potential_value": 28.0, "loss_window_days": 7, "daily_impact": 111.11}
    metrics = _action_priority_metrics(item)
    assert metrics["daily_loss"] == 111.11


def test_dead_inventory_daily_impact_from_insight_field():
    summary = {
        "insights": [
            {
                "title": "Dead Inventory",
                "severity": "medium",
                "potential_value": 900.0,
                "daily_impact": 10.0,
                "loss_window_days": 14,
                "routing_type": "dead_inventory",
                "problem": "2 SKUs never sold.",
                "action": "Discount and bundle.",
                "exact_items": ["Widget — SKU A1 — inventory 5 — 90d sales 0 — est. value $500.00"],
            }
        ],
        "anomalies": {
            "no_sales_products": [
                {
                    "product_title": "Widget",
                    "primary_sku": "A1",
                    "total_available": 5,
                    "est_on_hand_value": 500.0,
                }
            ]
        },
        "inventory": {"low_stock": [], "critical_stock": [], "out_of_stock": []},
        "customers": {"churned": [], "loyal": []},
        "revenue": {"high_return_rate": [], "trend": {}},
    }
    actions = build_structured_actions(summary, max_actions=5)
    dead = next(a for a in actions if str(a.get("email_routing_type")).lower() == "dead_inventory")
    assert dead["daily_loss"] == 10.0


def test_recoverable_and_projected_loss_formulas():
    item = {"potential_value": 200.0, "impact_type": "recoverable", "loss_window_days": 7}
    assert recoverable_opportunity(item) == 200.0
    assert projected_7d_loss(item) == 90.0

    risk_item = {"potential_value": 800.0, "impact_type": "risk", "loss_window_days": 7}
    assert recoverable_opportunity(risk_item) == 0.0
    assert projected_7d_loss(risk_item) == 800.0


def test_dead_inventory_action_includes_no_sales_products():
    summary = {
        "insights": [
            {
                "category": "inventory",
                "title": "Dead Inventory",
                "severity": "medium",
                "problem": "2 active product(s) have never sold but still have inventory.",
                "impact": "$800.00 estimated cash tied up.",
                "action": "Move dead stock today.",
                "potential_value": 800.0,
                "loss_window_days": 14,
                "routing_type": "dead_inventory",
                "exact_items": ["Widget — SKU A1 — inventory 5 — 90d sales 0 — est. value $500.00"],
            }
        ],
        "anomalies": {
            "no_sales_products": [
                {
                    "product_title": "Widget",
                    "primary_sku": "A1",
                    "total_available": 5,
                    "est_on_hand_value": 500.0,
                }
            ]
        },
        "inventory": {"low_stock": [], "critical_stock": [], "out_of_stock": []},
        "customers": {"churned": [], "loyal": []},
        "revenue": {"high_return_rate": [], "trend": {}},
    }
    assert len(_dead_inventory_items(summary)) >= 1
    actions = build_structured_actions(summary, max_actions=5)
    routes = {str(a.get("email_routing_type") or "").lower() for a in actions}
    assert "dead_inventory" in routes
