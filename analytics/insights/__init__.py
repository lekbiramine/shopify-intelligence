from analytics.customers import get_churned_customers, get_loyal_customers
from analytics.revenue import get_high_return_rate_products
from analytics.anomalies import (
    get_duplicate_orders,
    get_abnormal_discount_orders,
    get_products_with_no_sales,
)
from analytics.insights.insight_low_repeat_purchase_rate import run_insight as run_low_repeat_purchase_rate_insight
from analytics.insights.insight_high_value_customer_at_risk import run_insight as run_high_value_customer_at_risk_insight
from analytics.insights.insight_abandoned_checkout_spike import run_insight as run_abandoned_checkout_spike_insight
from analytics.insights.insight_low_margin_products import run_insight as run_low_margin_products_insight
import psycopg2
from psycopg2.extras import RealDictCursor
from config import settings
from config.logging_config import get_logger

logger = get_logger(__name__)


def _build_insight(
    category: str,
    title: str,
    severity: str,
    problem: str,
    impact: str,
    action: str,
    potential_value: float = 0.0,
    action_cta: str | None = None,
    execution_note: str | None = None,
    impact_type: str = "recoverable",
    is_generatable: bool = False,
    primary_entity_id: str | None = None,
    how_calculated: str | None = None,
    time_window: str | None = None,
    exact_items: list[str] | None = None,
    expected_outcome: str | None = None,
    confidence: str = "high",
    time_required_minutes: int | None = None,
    loss_window_days: int | None = None,
    routing_type: str | None = None,
) -> dict:
    return {
        "category": category,
        "title": title,
        "severity": severity,
        "problem": problem,
        "impact": impact,
        "action": action,
        "potential_value": float(potential_value or 0.0),
        "action_cta": action_cta or action,
        "execution_note": execution_note or "",
        "impact_type": impact_type,
        "is_generatable": bool(is_generatable),
        "primary_entity_id": primary_entity_id,
        "how_calculated": (how_calculated or "").strip(),
        "time_window": (time_window or "").strip(),
        "exact_items": exact_items or [],
        "expected_outcome": (expected_outcome or "").strip(),
        "confidence": (confidence or "high").strip().lower(),
        "time_required_minutes": int(time_required_minutes) if time_required_minutes is not None else None,
        "loss_window_days": int(loss_window_days) if loss_window_days is not None else None,
        "routing_type": (routing_type or "").strip().lower() or None,
    }


def insight_churned_customers(store_id: int) -> dict | None:
    churned = get_churned_customers(store_id)
    if not churned:
        return None

    count = len(churned)
    estimated_recovery = sum(float(c.get("total_spent", 0) or 0) / max(int(c.get("orders_count", 1) or 1), 1) for c in churned)
    top_targets = sorted(churned, key=lambda c: float(c.get("total_spent", 0) or 0), reverse=True)[:8]
    exact_items = []
    for c in top_targets:
        name = " ".join(
            p for p in [(c.get("first_name") or "").strip(), (c.get("last_name") or "").strip()] if p
        ).strip()
        label = name or (c.get("email") or "").strip() or f"Customer #{c.get('customer_id')}"
        days = c.get("days_since_last_order")
        days_txt = f"{round(float(days))}d since last order" if days is not None else "no orders yet"
        avg_order = float(c.get("total_spent", 0) or 0) / max(int(c.get("orders_count", 1) or 1), 1)
        exact_items.append(f"{label} — {days_txt} — est. AOV ${avg_order:,.2f}")

    return _build_insight(
        category="customers",
        title="Churned Customers",
        severity="high",
        problem=f"{count} customer(s) inactive for 90+ days.",
        impact=f"Estimated recovery opportunity: ${estimated_recovery:,.2f}",
        action="Email customers inactive >90 days with a 10% reactivation offer that expires in 48 hours (send to top spenders first).",
        potential_value=estimated_recovery,
        how_calculated="Sum over churned customers of (total_spent / orders_count), estimating one additional typical order if reactivated.",
        time_window="Churned = no order in the last 90+ days (or never ordered).",
        exact_items=exact_items,
        expected_outcome="Recover 1–3 orders quickly and reduce churn risk over the next 7 days.",
        confidence="medium",
        time_required_minutes=12,
        loss_window_days=7,
        impact_type="recoverable",
        is_generatable=True,
        routing_type="churned_customers",
    )


def insight_high_return_rate(store_id: int) -> list[dict]:
    products = get_high_return_rate_products(store_id)
    insights = []
    for p in products:
        rate = float(p.get("return_rate", 0)) * 100
        returned_units = float(p.get("total_returned", 0) or 0)
        est_loss = returned_units * 20.0
        insights.append(
            _build_insight(
                category="revenue",
                title="High Return Rate Product",
                severity="high",
                problem=f"Product \"{p['product_title']}\" has a {rate:.1f}% return rate.",
                impact=f"~${est_loss:,.2f} potential loss from {returned_units:g} returned units.",
                action=f"Pause paid ads for {p['product_title']} today until return rate drops below 20% (fix listing + fulfillment first).",
                potential_value=est_loss,
                exact_items=[
                    f"{p.get('product_title')} (product_id={p.get('product_id')}) — return rate {rate:.1f}% — returned units {returned_units:g}"
                ],
                expected_outcome="Stop wasting ad spend on a leaky product and reduce refunds/chargebacks this week.",
                confidence="low",
                time_required_minutes=10,
                loss_window_days=7,
                routing_type="high_return_rate",
            )
        )
    return insights


def insight_dead_inventory(store_id: int) -> list[dict]:
    products = get_products_with_no_sales(store_id)
    if not products:
        return []

    n = len(products)
    total_value = sum(float(p.get("est_on_hand_value", 0) or 0) for p in products)
    top_items = sorted(products, key=lambda p: float(p.get("est_on_hand_value", 0) or 0), reverse=True)[:8]
    exact_items = []
    for p in top_items:
        title = p.get("product_title") or "Unknown product"
        qty = int(p.get("total_available", 0) or 0)
        val = float(p.get("est_on_hand_value", 0) or 0)
        sku_txt = str(p.get("primary_sku") or "").strip()
        sku_part = f"SKU {sku_txt} — " if sku_txt else ""
        exact_items.append(f"{title} — {sku_part}inventory {qty} — 90d sales 0 — est. value ${val:,.2f}")

    return [
        _build_insight(
            category="inventory",
            title="Dead Inventory",
            severity="medium",
            problem=f"{n} active product(s) have never sold but still have inventory.",
            impact=f"${total_value:,.2f} estimated cash tied up in never-sold inventory.",
            action="Move dead stock today: discount 20% and bundle with your best-seller (apply to the top dead SKUs only).",
            potential_value=float(total_value),
            how_calculated="Estimate = SUM(on_hand_units) * AVG(variant_price) for products with zero historical order_items.",
            time_window="Dead inventory = active products that never appeared in any order (lifetime).",
            exact_items=exact_items,
            expected_outcome="Recover cash quickly and reduce storage/working-capital drag in 7–14 days.",
            confidence="medium",
            time_required_minutes=25,
            loss_window_days=14,
            routing_type="dead_inventory",
        )
    ]


def insight_high_value_customers(store_id: int) -> dict | None:
    loyal = get_loyal_customers(store_id)
    if not loyal:
        return None
    all_loyal_revenue = sum(float(c.get("total_spent", 0) or 0) for c in loyal)
    top2 = loyal[:2]
    top2_revenue = sum(float(c.get("total_spent", 0) or 0) for c in top2)
    pct = (top2_revenue / all_loyal_revenue * 100) if all_loyal_revenue > 0 else 0.0
    exact_items = []
    for c in loyal[:5]:
        label = " ".join(
            p for p in [(c.get("first_name") or "").strip(), (c.get("last_name") or "").strip()] if p
        ).strip() or (c.get("email") or "").strip() or f"Customer #{c.get('customer_id')}"
        spend = float(c.get("total_spent") or 0.0)
        oc = int(c.get("orders_count") or 0)
        exact_items.append(f"{label} — SPEND: ${spend:.2f} — ORDERS: {oc}")
    return _build_insight(
        category="customers",
        title="Revenue Concentration Risk",
        severity="medium" if pct >= 40 else "low",
        problem=f"Top 2 loyal customers generate {pct:.1f}% of loyal revenue.",
        impact=f"${top2_revenue:,.2f} concentrated in 2 customers (dependency risk).",
        action="Reduce dependency today: target one-time buyers with a second-purchase offer and retarget recent visitors with your top seller.",
        potential_value=top2_revenue,
        impact_type="risk",
        exact_items=exact_items,
        routing_type="revenue_concentration",
    )


def insight_abnormal_discounts(store_id: int) -> list[dict]:
    return [
        _build_insight(
            category="anomalies",
            title="Abnormal Discount Detected",
            severity="high",
            problem=f"Order {o['order_id']} has a {o['discount_pct']}% discount.",
            impact=f"Potential revenue leakage on order value due to {o['discount_pct']}% discount.",
            action="Fix the discount rule today or refund/correct the order if needed.",
            potential_value=float(o.get("total_discounts", 0) or 0),
            routing_type="abnormal_discount",
        )
        for o in get_abnormal_discount_orders(store_id)
    ]


def insight_duplicate_orders(store_id: int) -> list[dict]:
    return [
        _build_insight(
            category="anomalies",
            title="Duplicate Order Detected",
            severity="high",
            problem=f"Customer {o['customer_id']} placed {o['order_count']} duplicate orders of ${float(o['total_price']):,.2f}.",
            impact=f"Charge exposure: ${float(o.get('total_price', 0)) * (int(o.get('order_count', 1)) - 1):,.2f}",
            action="Check for duplicate charge today and refund if needed.",
            potential_value=float(o.get("total_price", 0)) * max(int(o.get("order_count", 1)) - 1, 0),
            routing_type="duplicate_orders",
        )
        for o in get_duplicate_orders(store_id)
    ]


def _build_signal_style_insight(signal: dict) -> dict:
    action_type = str(signal.get("action_type") or "").strip().lower()
    title_by_type = {
        "low_repeat_purchase_rate": "Low Repeat Purchase Rate",
        "high_value_customer_at_risk": "High-Value Customers At Risk",
        "abandoned_checkout_spike": "Abandoned Checkout Spike",
        "low_margin_products": "Low Margin Product",
    }
    severity_by_type = {
        "low_repeat_purchase_rate": "high",
        "high_value_customer_at_risk": "high",
        "abandoned_checkout_spike": "high",
        "low_margin_products": "medium",
    }
    impact_type_by_type = {
        "low_repeat_purchase_rate": "recoverable",
        "high_value_customer_at_risk": "risk",
        "abandoned_checkout_spike": "recoverable",
        "low_margin_products": "recoverable",
    }
    targets = list(signal.get("targets") or [])
    exact_items: list[str] = []
    for target in targets:
        if isinstance(target, dict):
            name = str(target.get("name") or "Unknown")
            sku = str(target.get("sku") or "").strip()
            days_since = target.get("days_since_order")
            ltv = target.get("ltv")
            parts = [name]
            if sku:
                parts.append(f"SKU {sku}")
            if days_since is not None:
                parts.append(f"{int(round(float(days_since)))} days since last order")
            if ltv is not None and float(ltv) > 0:
                # No thousands separators — email target parsers must capture full dollar amount.
                parts.append(f"LTV ${float(ltv):.2f}")
            if action_type == "low_margin_products":
                price = float(target.get("price") or 0.0)
                units = int(target.get("units_sold") or 0)
                parts.append(f"price ${price:.2f} — units sold 90d {units}")
            exact_items.append(" — ".join(parts))
        else:
            text = str(target).strip()
            if text:
                exact_items.append(text)

    return _build_insight(
        category="revenue",
        title=title_by_type.get(action_type, action_type.replace("_", " ").title()),
        severity=severity_by_type.get(action_type, "medium"),
        problem=str(signal.get("problem") or "Signal detected."),
        impact=f"Estimated 7-day value: ${float(signal.get('seven_day_projection') or 0.0):,.2f}",
        action=str(signal.get("fix") or "Take corrective action."),
        potential_value=float(signal.get("total_value") or 0.0),
        impact_type=impact_type_by_type.get(action_type, "recoverable"),
        exact_items=exact_items,
        expected_outcome=f"Projected 7-day effect: ${float(signal.get('seven_day_projection') or 0.0):,.2f}",
        confidence="medium",
        time_required_minutes=20,
        loss_window_days=7,
        routing_type=str(action_type or "").strip().lower() or None,
    )


def _run_new_insight_signal(store_id: int, signal_runner) -> dict | None:
    with psycopg2.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        dbname=settings.DB_NAME,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
    ) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            result = signal_runner(cursor)
    if not result or not bool(result.get("detected")):
        return None
    return _build_signal_style_insight(result)


def build_insights(store_id: int) -> list[dict]:
    logger.info("Building insights...")
    severity_order = {"high": 0, "medium": 1, "low": 2}
    insights = []
    for fn in [insight_churned_customers, insight_high_value_customers]:
        result = fn(store_id)
        if result:
            insights.append(result)
    for fn in [insight_high_return_rate, insight_dead_inventory, insight_abnormal_discounts, insight_duplicate_orders]:
        insights.extend(fn(store_id))
    for fn in [
        run_low_repeat_purchase_rate_insight,
        run_high_value_customer_at_risk_insight,
        run_abandoned_checkout_spike_insight,
        run_low_margin_products_insight,
    ]:
        extra = _run_new_insight_signal(store_id, fn)
        if extra:
            insights.append(extra)
    insights.sort(key=lambda x: severity_order.get(x["severity"], 99))
    logger.info("Built %s insights.", len(insights))
    return insights
