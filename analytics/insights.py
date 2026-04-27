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
    }


def insight_churned_customers(store_id: int) -> dict | None:
    churned = get_churned_customers(store_id)
    if not churned:
        return None

    count = len(churned)
    estimated_lost = sum(
        float(c.get("total_spent", 0)) / max(c.get("orders_count", 1), 1)
        for c in churned
    )

    return _build_insight(
        category="customers",
        title="Churned Customers",
        severity="high",
        problem=f"{count} customer(s) inactive for 90+ days.",
        impact=f"Estimated recovery opportunity: ${estimated_lost:,.2f}",
        action="Generate win-back email + export customer list, then send a 10% code today.",
        potential_value=estimated_lost,
        action_cta="Generate win-back email / Export customer list",
        execution_note=(
            "Ready-to-send template:\n"
            "Subject: We miss you — here's 10% off\n"
            "Hi {{name}},\n"
            "It's been a while since your last order and we'd love to have you back.\n"
            "Use code WELCOME10 for 10% off your next order this week."
        ),
        impact_type="recoverable",
        is_generatable=True,
    )


def insight_high_return_rate(store_id: int) -> list[dict]:
    products = get_high_return_rate_products(store_id)
    insights = []

    for p in products:
        rate = float(p.get("return_rate", 0)) * 100
        insights.append(_build_insight(
            category="revenue",
            title="High Return Rate Product",
            severity="high",
            problem=f"Product \"{p['product_title']}\" has a {rate:.1f}% return rate.",
            impact=(
                f"~${float(p.get('total_returned', 0)) * 20:,.2f} "
                f"potential loss from {p['total_returned']} returned units."
            ),
            action=(
                f"Pause ads for {p['product_title']} immediately."
            ),
            potential_value=float(p.get("total_returned", 0)) * 20.0,
            action_cta=f"Pause ads for {p['product_title']}",
            execution_note=(
                "Checklist:\n"
                "- Check recent reviews mentioning defects\n"
                "- Compare product delivered vs listing images\n"
                "- Contact supplier if defect confirmed"
            ),
            impact_type="recoverable",
            primary_entity_id=str(p.get("product_id")),
        ))

    return insights


def insight_dead_inventory(store_id: int) -> list[dict]:
    products = get_products_with_no_sales(store_id)
    if not products:
        return []

    n = len(products)
    if n == 1:
        problem = "1 product has inventory but no sales."
    else:
        problem = f"{n} products have inventory but no sales."

    return [
        _build_insight(
            category="inventory",
            title="Dead Inventory",
            severity="medium",
            problem=problem,
            impact=f"${n * 25:,.2f} locked in unsold products ({n} items).",
            action="Run a dead inventory recovery sprint this week.",
            potential_value=float(n * 25),
            execution_note=(
                "- Apply 15-25% discount to top 5 dead items\n"
                "- Bundle slow products with best-sellers\n"
                "- Stop reordering these SKUs"
            ),
            impact_type="recoverable",
        )
    ]


def insight_high_value_customers(store_id: int) -> dict | None:
    loyal = get_loyal_customers(store_id)
    if not loyal:
        return None

    top_10 = loyal[:10]
    total_revenue_top = sum(float(c.get("total_spent", 0)) for c in top_10)
    all_revenue = sum(float(c.get("total_spent", 0)) for c in loyal)
    pct = (total_revenue_top / all_revenue * 100) if all_revenue > 0 else 0

    if len(loyal) >= 10:
        return _build_insight(
            category="customers",
            title="High-Value Customers",
            severity="low",
            problem=f"Top 10 customers generated {pct:.1f}% of total loyal revenue.",
            impact=f"${total_revenue_top:,.2f} revenue concentrated in top buyers.",
            action="Offer VIP perks and retention campaigns to protect this revenue base.",
            potential_value=total_revenue_top,
            action_cta="Launch VIP retention campaign",
        )

    return _build_insight(
        category="customers",
        title="Revenue Concentration Risk",
        severity="medium",
        problem=f"Revenue depends on only {len(top_10)} customers.",
        impact=f"${total_revenue_top:,.2f} at risk if one customer churns.",
        action="Run campaigns targeting new customers and reduce reliance on repeat buyers.",
        potential_value=total_revenue_top,
        execution_note=(
            "- Run campaigns targeting new customers\n"
            "- Avoid relying only on repeat buyers"
        ),
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
            action="Verify the discount was intentional or issue a correction.",
            potential_value=float(o.get("total_discounts", 0) or 0),
            action_cta="Audit discount rule immediately",
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
            action="Verify payment and issue a refund if necessary.",
            potential_value=float(o.get("total_price", 0)) * max(int(o.get("order_count", 1)) - 1, 0),
            action_cta="Verify payment and refund duplicates",
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