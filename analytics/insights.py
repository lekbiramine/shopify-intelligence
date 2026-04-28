from analytics.inventory import get_out_of_stock_products
from analytics.customers import get_churned_customers, get_loyal_customers
from analytics.revenue import get_high_return_rate_products, get_revenue_by_product
from analytics.anomalies import (
    get_duplicate_orders,
    get_abnormal_discount_orders,
    get_products_with_no_sales,
)
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
    }


def insight_churned_customers(store_id: int) -> dict | None:
    churned = get_churned_customers(store_id)
    if not churned:
        return None

    count = len(churned)
    # Conservative: estimate one additional "typical" order per churned customer.
    # avg_order_value ~= total_spent / orders_count (fallback orders_count=1).
    estimated_recovery = sum(float(c.get("total_spent", 0) or 0) / max(int(c.get("orders_count", 1) or 1), 1) for c in churned)
    top_targets = sorted(churned, key=lambda c: float(c.get("total_spent", 0) or 0), reverse=True)[:8]
    exact_items = []
    for c in top_targets:
        name = " ".join(p for p in [(c.get("first_name") or "").strip(), (c.get("last_name") or "").strip()] if p).strip()
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
        action_cta="Email inactive >90d customers with 48h 10% offer (top spenders first)",
        execution_note=(
            "Ready-to-send template:\n"
            "Subject: We miss you — here's 10% off\n"
            "Hi {{name}},\n"
            "It's been a while since your last order and we'd love to have you back.\n"
            "Use code WELCOME10 for 10% off your next order this week."
        ),
        how_calculated="Sum over churned customers of (total_spent / orders_count), estimating one additional typical order if reactivated.",
        time_window="Churned = no order in the last 90+ days (or never ordered).",
        exact_items=exact_items,
        expected_outcome="Recover 1–3 orders quickly and reduce churn risk over the next 7 days.",
        confidence="medium",
        time_required_minutes=12,
        loss_window_days=7,
        impact_type="recoverable",
        is_generatable=True,
    )


def insight_high_return_rate(store_id: int) -> list[dict]:
    products = get_high_return_rate_products(store_id)
    insights = []

    for p in products:
        rate = float(p.get("return_rate", 0)) * 100
        returned_units = float(p.get("total_returned", 0) or 0)
        est_loss = returned_units * 20.0
        insights.append(_build_insight(
            category="revenue",
            title="High Return Rate Product",
            severity="high",
            problem=f"Product \"{p['product_title']}\" has a {rate:.1f}% return rate.",
            impact=(
                f"~${est_loss:,.2f} potential loss from {returned_units:g} returned units."
            ),
            action=f"Pause paid ads for {p['product_title']} today until return rate drops below 20% (fix listing + fulfillment first).",
            potential_value=est_loss,
            action_cta=f"Pause paid ads for {p['product_title']} until return rate <20%",
            execution_note=(
                "Checklist:\n"
                "- Check recent reviews mentioning defects\n"
                "- Compare product delivered vs listing images\n"
                "- Contact supplier if defect confirmed"
            ),
            how_calculated="Estimated loss = returned_units * $20 placeholder (replace with your true gross-margin-per-unit for accuracy).",
            time_window="Return rate calculated from your loaded order/return signals (see `analytics.revenue.get_high_return_rate_products`).",
            exact_items=[f"{p.get('product_title')} (product_id={p.get('product_id')}) — return rate {rate:.1f}% — returned units {returned_units:g}"],
            expected_outcome="Stop wasting ad spend on a leaky product and reduce refunds/chargebacks this week.",
            confidence="low",
            time_required_minutes=10,
            loss_window_days=7,
            impact_type="recoverable",
            primary_entity_id=str(p.get("product_id")),
        ))

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
        exact_items.append(f"{title} — on hand {qty} — est. value ${val:,.2f}")

    problem = f"{n} active product(s) have never sold but still have inventory."

    return [
        _build_insight(
            category="inventory",
            title="Dead Inventory",
            severity="medium",
            problem=problem,
            impact=f"${total_value:,.2f} estimated cash tied up in never-sold inventory.",
            action="Move dead stock today: discount 20% and bundle with your best-seller (apply to the top dead SKUs only).",
            potential_value=float(total_value),
            action_cta="Move dead stock: 20% off + bundle with best-seller (top items only)",
            execution_note=(
                "- Apply 15-25% discount to top 5 dead items\n"
                "- Bundle slow products with best-sellers\n"
                "- Stop reordering these SKUs"
            ),
            how_calculated="Estimate = SUM(on_hand_units) * AVG(variant_price) for products with zero historical order_items.",
            time_window="Dead inventory = active products that never appeared in any order (lifetime).",
            exact_items=exact_items,
            expected_outcome="Recover cash quickly and reduce storage/working-capital drag in 7–14 days.",
            confidence="medium",
            time_required_minutes=25,
            loss_window_days=14,
            impact_type="recoverable",
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
    for c in top2:
        name = " ".join(p for p in [(c.get("first_name") or "").strip(), (c.get("last_name") or "").strip()] if p).strip()
        label = name or (c.get("email") or "").strip() or f"Customer #{c.get('customer_id')}"
        exact_items.append(f"{label} — spent ${float(c.get('total_spent', 0) or 0):,.2f} across {int(c.get('orders_count', 0) or 0)} orders")

    return _build_insight(
        category="customers",
        title="Revenue Concentration Risk",
        severity="medium" if pct >= 40 else "low",
        problem=f"Top 2 loyal customers generate {pct:.1f}% of loyal revenue.",
        impact=f"${top2_revenue:,.2f} concentrated in 2 customers (dependency risk).",
        action="Reduce dependency today: target one-time buyers with a second-purchase offer and retarget recent visitors with your top seller.",
        potential_value=top2_revenue,
        action_cta="Reduce dependency: second-purchase offer + retarget top seller",
        execution_note=(
            "- Email one-time buyers with a 2nd-order incentive\n"
            "- Retarget recent site visitors with a best-seller offer\n"
            "- Add post-purchase flow to push a second purchase within 14 days"
        ),
        how_calculated="Concentration = (sum spend of top 2 loyal customers) / (sum spend of all loyal customers).",
        time_window="Loyal = customers with orders_count >= threshold (see `config.constants.HIGH_VALUE_ORDER_COUNT`).",
        exact_items=exact_items,
        expected_outcome="Reduce dependency risk and stabilize weekly revenue within 2–4 weeks.",
        confidence="high",
        time_required_minutes=20,
        loss_window_days=30,
        impact_type="risk",
    )


def insight_abnormal_discounts(store_id: int) -> list[dict]:
    orders = get_abnormal_discount_orders(store_id)
    insights = []

    for o in orders:
        insights.append(_build_insight(
            category="anomalies",
            title="Abnormal Discount Detected",
            severity="high",
            problem=f"Order {o['order_id']} has a {o['discount_pct']}% discount.",
            impact=f"Potential revenue leakage on order value due to {o['discount_pct']}% discount.",
            action="Fix the discount rule today or refund/correct the order if needed.",
            potential_value=float(o.get("total_discounts", 0) or 0),
            action_cta="Audit discount rule immediately",
            time_required_minutes=8,
            loss_window_days=7,
            impact_type="recoverable",
        ))

    return insights


def insight_duplicate_orders(store_id: int) -> list[dict]:
    orders = get_duplicate_orders(store_id)
    insights = []

    for o in orders:
        insights.append(_build_insight(
            category="anomalies",
            title="Duplicate Order Detected",
            severity="high",
            problem=(
                f"Customer {o['customer_id']} placed {o['order_count']} orders "
                f"of ${float(o['total_price']):,.2f} on {o['order_date']}."
            ),
            impact=f"Charge exposure: ${float(o.get('total_price', 0)) * (int(o.get('order_count', 1)) - 1):,.2f}",
            action="Check for duplicate charge today and refund if needed.",
            potential_value=float(o.get("total_price", 0)) * max(int(o.get("order_count", 1)) - 1, 0),
            action_cta="Verify payment and refund duplicates",
            time_required_minutes=6,
            loss_window_days=7,
            impact_type="recoverable",
        ))

    return insights


def build_insights(store_id: int) -> list[dict]:
    """
    Aggregates all insights into a flat list sorted by severity.
    """
    logger.info("Building insights...")

    severity_order = {"high": 0, "medium": 1, "low": 2}
    insights = []

    # Single insights
    for fn in [insight_churned_customers, insight_high_value_customers]:
        result = fn(store_id)
        if result:
            insights.append(result)

    # List insights
    for fn in [insight_high_return_rate, insight_dead_inventory, insight_abnormal_discounts, insight_duplicate_orders]:
        insights.extend(fn(store_id))

    insights.sort(key=lambda x: severity_order.get(x["severity"], 99))

    logger.info(f"Built {len(insights)} insights.")
    return insights