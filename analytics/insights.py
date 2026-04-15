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
) -> dict:
    return {
        "category": category,
        "title": title,
        "severity": severity,
        "problem": problem,
        "impact": impact,
        "action": action,
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
        impact=f"Estimated lost revenue: ${estimated_lost:,.2f}",
        action="Send a win-back email with a 10% discount code.",
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
            impact=f"{p['total_returned']} out of {p['total_sold']} units returned.",
            action="Review product quality, update listings, consider pausing ads.",
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
            impact="Capital is tied up in unsold stock.",
            action="Review pricing, bundles, or discontinue slow movers.",
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

    return _build_insight(
        category="customers",
        title="High-Value Customers",
        severity="low",
        problem=f"Top 10 customers generated {pct:.1f}% of total loyal revenue.",
        impact=f"${total_revenue_top:,.2f} revenue concentrated in {len(top_10)} customers.",
        action="Offer VIP perks, early access, or exclusive discounts to retain them.",
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
            impact="Potential revenue loss due to pricing error or abuse.",
            action="Verify the discount was intentional or issue a correction.",
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
            impact="Customer may have been charged multiple times.",
            action="Verify payment and issue a refund if necessary.",
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