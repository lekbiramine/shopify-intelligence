from __future__ import annotations


def _to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _to_str(value: object, default: str = "") -> str:
    text = str(value).strip() if value is not None else ""
    return text or default


def _safe_int_div(numerator: float, denominator: float, default: int = 0) -> int:
    if denominator <= 0:
        return default
    return int(numerator / denominator)


def _safe_inverse_int(value: float, default: int = 0) -> int:
    if value <= 0:
        return default
    return int(1 / value)


def get_action_advice(action_type: str, metrics: dict) -> dict:
    """
    Returns a dict with keys:
    - 'headline': str — one punchy line summarizing the stakes
    - 'context': str — why this matters, using their actual numbers
    - 'playbook': list[str] — 2-4 concrete steps to execute
    - 'benchmark': str — industry reference point to make it feel real
    - 'urgency': str — what happens specifically to THEIR store if ignored
    """
    m = metrics or {}
    normalized_type = str(action_type or "").strip().lower()

    if normalized_type == "dead_inventory":
        sku_count = _to_int(m.get("sku_count"), 0)
        total_units = _to_int(m.get("total_units"), 0)
        days_stale = _to_int(m.get("days_stale"), 90)
        estimated_value = _to_float(m.get("estimated_value"), 0.0)
        raw_store_aov = _to_float(m.get("store_aov"), 0.0)
        store_aov = raw_store_aov if raw_store_aov > 0 else 35.00
        offset_orders = _safe_int_div(estimated_value, store_aov, 0)
        return {
            "headline": f"{sku_count} SKUs have been silent for {days_stale} days - that's ${estimated_value:.2f} earning 0% return",
            "context": (
                f"Dead inventory is not a storage problem, it's a cash flow problem. Every day these {total_units} units sit unsold, "
                "you're paying for storage while competitors discount similar products and take your potential buyers. Hormozi calls this "
                "'zombie capital' - assets that look real on paper but generate zero velocity."
            ),
            "playbook": [
                "Create a bundle: pair each dead SKU with your best-selling product at a 10-15% combined discount. Bundling increases AOV while moving dead stock without destroying brand perception.",
                f"Run a 72-hour flash sale specifically for these {sku_count} SKUs. Scarcity + deadline = action. Email your list with subject line: 'We found {total_units} forgotten items in our warehouse.'",
                "If units don't move in 14 days, list them on a secondary channel (eBay, Facebook Marketplace) at cost. Recovering cost beats writing off inventory.",
                "Never reorder these SKUs until you understand WHY they didn't sell - wrong price, wrong audience, wrong season, or wrong product entirely.",
            ],
            "benchmark": (
                "Industry standard: inventory that doesn't turn in 90 days costs merchants 20-30% of its value annually in holding costs "
                "and opportunity cost (Shopify Merchant Research, 2023)."
            ),
            "urgency": (
                f"At your current AOV of ${store_aov:.2f}, you need to sell {offset_orders} more orders just to offset what this dead stock "
                "is costing you in opportunity. Every week you wait adds to that deficit."
            ),
        }

    if normalized_type == "high_return_rate":
        product_name = _to_str(m.get("product_name"), "This product")
        return_rate = max(_to_float(m.get("return_rate"), 0.0), 0.0)
        returned_units = _to_int(m.get("returned_units"), 0)
        revenue_lost = _to_float(m.get("revenue_lost"), 0.0)
        per_regret = _safe_inverse_int(return_rate, 0)
        return {
            "headline": (
                f"{product_name} is being returned at {return_rate*100:.1f}% - {returned_units} units back on your shelf, "
                f"${revenue_lost:.2f} reversed"
            ),
            "context": (
                f"A {return_rate*100:.1f}% return rate means nearly 1 in {per_regret} customers who buy {product_name} regret it. "
                "This is not a logistics problem - it's an expectation mismatch. Your listing is promising something the product "
                "isn't delivering. The healthy benchmark for e-commerce is under 5%. "
                f"You are at {return_rate*100:.1f}%."
            ),
            "playbook": [
                f"Pause all paid ads driving traffic to {product_name} immediately. You are paying to acquire customers who will return the product - that's negative ROI on every ad dollar spent.",
                f"Email every customer who returned {product_name} with one question: 'What did you expect that you didn't get?' 3 responses will tell you everything. Use Hormozi's feedback loop: the customer who returns is more valuable than the one who stays silent and churns.",
                "Rewrite the product description and photos to show exactly what the product is, not what you wish it was. Specificity reduces returns. Vague listings attract wrong buyers.",
                "If return rate doesn't drop below 15% in 30 days after fixing the listing, consider discontinuing the product. Some products are fundamentally mismatched to your audience.",
            ],
            "benchmark": (
                "Shopify data shows return rates above 15% on a single product typically indicate a listing problem, not a product problem. "
                "Above 30% indicates either a quality issue or a fundamental product-market mismatch."
            ),
            "urgency": (
                f"Every additional sale of {product_name} before you fix this has a {return_rate*100:.1f}% chance of becoming a return, "
                "a support ticket, and a potential chargeback. You're not growing revenue on this SKU - you're cycling it."
            ),
        }

    if normalized_type == "churned_customers":
        churned_count = _to_int(m.get("churned_count"), 0)
        avg_days_since_order = _to_float(m.get("avg_days_since_order"), 60.0)
        store_aov = _to_float(m.get("store_aov"), 0.0) or 35.00
        potential_recovery = _to_float(m.get("potential_recovery"), 0.0)
        top_churned_product = _to_str(m.get("top_churned_product"), "your top churned category")
        return {
            "headline": f"{churned_count} customers ghosted your store - conservative reactivation value: ${potential_recovery:.2f}",
            "context": (
                f"These {churned_count} customers already bought from you. They handed you their credit card once. The hardest part is done. "
                "Hormozi's core principle: reactivating a past customer costs 5-7x less than acquiring a new one. "
                f"You have {churned_count} people sitting in your database right now who already trust you enough to have bought - and "
                "you're spending money on ads to find strangers instead."
            ),
            "playbook": [
                f"Send a reactivation email to all {churned_count} contacts today. Subject line: 'We noticed you haven't been back.' Body: one sentence acknowledging the gap, one specific offer (10% off their next order), one direct link. No fluff. Klaviyo data shows this format outperforms 'we miss you' emails by 34%.",
                f"Segment by last product purchased. Customers who last bought {top_churned_product} should get an email specifically about that category - not a generic store discount.",
                "Set up a 3-email win-back sequence: Day 1 (soft check-in), Day 4 (specific offer), Day 10 (last chance + slightly better offer). Stop the sequence the moment they buy. Most reactivations happen on email 2.",
                "Anyone who doesn't respond to all 3 emails moves to a quarterly newsletter only. Don't burn your list chasing people who are truly gone.",
            ],
            "benchmark": (
                f"Industry win-back sequences average 10-15% reactivation rates. At {churned_count} churned customers and ${store_aov:.2f} AOV, "
                f"a 10% reactivation = {int(churned_count * 0.10)} orders = ${churned_count * 0.10 * store_aov:.2f} in recovered revenue."
            ),
            "urgency": (
                "Every 30 days these customers go without hearing from you, reactivation probability drops by roughly 8-12%. "
                f"{churned_count} customers who last ordered {avg_days_since_order:.0f} days ago are still reachable. "
                "At 120 days they're effectively gone."
            ),
        }

    if normalized_type == "low_repeat_purchase_rate":
        repeat_rate = max(_to_float(m.get("repeat_rate"), 0.0), 0.0)
        one_time_buyers = _to_int(m.get("one_time_buyers"), 0)
        store_aov = _to_float(m.get("store_aov"), 0.0) or 35.00
        revenue_if_10pct_improvement = _to_float(m.get("revenue_if_10pct_improvement"), 0.0)
        return {
            "headline": (
                f"Only {repeat_rate*100:.1f}% of your customers come back - {one_time_buyers} people bought once and never returned"
            ),
            "context": (
                "You are running a leaky bucket business. Every month you pour new customers in through ads and marketing, but "
                f"{(1-repeat_rate)*100:.1f}% of them leave and never return. Increasing your repeat purchase rate by just 10% would add "
                f"${revenue_if_10pct_improvement:.2f} to your revenue without spending a single dollar on ads. This is the highest ROI lever available to you right now."
            ),
            "playbook": [
                "Send a post-purchase email sequence to every new customer: Day 1 (order confirmation + what to expect), Day 3 (how to get the most out of their purchase), Day 14 (related products + 10% loyalty discount). This alone typically lifts repeat rate by 8-15%.",
                "Create a simple loyalty mechanic: 'Buy 3 times, get 15% off forever.' You don't need an app. A manual discount code sent after their 3rd order works. The goal is to make the 3rd purchase feel rewarded.",
                "Identify your top 10% of repeat buyers and find out what they have in common - same product entry point, same demographic, same traffic source. Then optimize your ads to acquire more people who look like them.",
                "Add a reorder prompt email at the natural replenishment cycle of your top products. If your best-selling product runs out in 30 days, send an email on day 25.",
            ],
            "benchmark": (
                "Shopify merchants with repeat purchase rates above 27% generate 3x the lifetime value per customer compared to those below 15%. "
                f"Your current rate of {repeat_rate*100:.1f}% puts you in the bottom tier - but a 10% improvement is achievable in 60 days with email alone."
            ),
            "urgency": (
                f"You have {one_time_buyers} one-time buyers in your database right now. If just 10% of them buy again at ${store_aov:.2f} AOV, "
                f"that's ${one_time_buyers * 0.10 * store_aov:.2f} in revenue that requires zero ad spend to capture."
            ),
        }

    if normalized_type == "high_value_customer_at_risk":
        customer_count = _to_int(m.get("customer_count"), 0)
        avg_ltv = _to_float(m.get("avg_ltv"), 0.0)
        days_since_last_order = _to_float(m.get("days_since_last_order"), 0.0)
        total_ltv_at_risk = _to_float(m.get("total_ltv_at_risk"), 0.0)
        store_aov = _to_float(m.get("store_aov"), 0.0) or 35.00
        replacement_acq = _safe_int_div(avg_ltv, store_aov, 0)
        return {
            "headline": (
                f"{customer_count} VIP customers are going quiet - ${total_ltv_at_risk:.2f} in lifetime value showing early churn signals"
            ),
            "context": (
                f"These are not average customers. Each one has spent an average of ${avg_ltv:.2f} in your store. "
                f"Losing one of them costs you the equivalent of {replacement_acq} new customer acquisitions. "
                "They haven't churned yet - they're showing early signals. This is the highest-value intervention available to you today."
            ),
            "playbook": [
                f"Email each of these {customer_count} customers personally - not a campaign, a direct email from your store owner account. One sentence: 'Hey [name], noticed you haven't been back in {days_since_last_order:.0f} days - is there anything we can do better?' This alone has a 20-30% response rate from VIPs according to Klaviyo case studies.",
                "Offer an exclusive VIP discount that is NOT available to your general list. 20% off, early access to new products, or free shipping for life on orders over $X. Make them feel like the category they are.",
                "Find out what they last bought and recommend the natural next product in that journey. VIP customers respond to curation, not promotion.",
                "If they respond, ask them what would make them a customer for life. Hormozi principle: the customer who tells you what they want and gets it will never leave.",
            ],
            "benchmark": (
                "Research shows the top 20% of e-commerce customers generate 80% of revenue. Losing a single VIP customer typically requires "
                "acquiring 5-8 new customers to replace their revenue contribution."
            ),
            "urgency": (
                f"At {days_since_last_order:.0f} days since their last order, these customers are in the early churn window. "
                "After 90 days the probability of reactivation drops below 20%. You have a narrow window to act before they become a win-back "
                "problem instead of a retention problem."
            ),
        }

    if normalized_type == "abandoned_checkout_spike":
        abandoned_count = _to_int(m.get("abandoned_count"), 0)
        abandonment_rate = max(_to_float(m.get("abandonment_rate"), 0.0), 0.0)
        potential_revenue = _to_float(m.get("potential_revenue"), 0.0)
        prev_week_abandonment_rate = max(_to_float(m.get("prev_week_abandonment_rate"), 0.0), 0.0)
        return {
            "headline": f"{abandoned_count} checkouts abandoned this week - ${potential_revenue:.2f} left at the door",
            "context": (
                f"Your abandonment rate jumped from {prev_week_abandonment_rate*100:.1f}% to {abandonment_rate*100:.1f}% this week. "
                "This is not normal variance - something changed. Either your shipping costs surprised people at checkout, your payment flow "
                "broke on a specific device, or a competitor started offering something you don't. This needs to be diagnosed today, not monitored."
            ),
            "playbook": [
                "Send an abandoned cart email within 1 hour of abandonment. Klaviyo data: emails sent within 1 hour recover 3x more revenue than emails sent at 24 hours. Subject line: 'You left something behind.' No discount in email 1 - just a direct link back to cart.",
                "Email 2 at 24 hours: add a 10% discount code with a 48-hour expiry. This recovers an additional 15-20% of remaining abandoned carts.",
                "Check your checkout page on mobile right now. 67% of abandonment spikes are caused by a mobile UX issue - a button that doesn't work, a form that breaks, or a payment method that disappeared.",
                "Add a one-click trust signal to your checkout: a visible return policy, a security badge, and a single testimonial from a real customer. Cialdini's principle: uncertainty at the point of purchase kills conversion.",
            ],
            "benchmark": (
                "Average e-commerce abandonment rate: 69-70%. Above 75% indicates a specific friction point. "
                f"Your current rate of {abandonment_rate*100:.1f}% needs immediate diagnosis."
            ),
            "urgency": (
                f"Every day this rate stays elevated costs you approximately ${potential_revenue / 7:.2f}. "
                f"At {abandoned_count} abandonments this week, recovering even 20% means ${potential_revenue * 0.20:.2f} in revenue this week alone."
            ),
        }

    if normalized_type in {"low_margin_products_selling_high", "low_margin_products"}:
        product_name = _to_str(m.get("product_name"), "This product")
        units_sold = _to_int(m.get("units_sold"), 0)
        estimated_margin = _to_float(m.get("estimated_margin"), 0.0)
        revenue_generated = _to_float(m.get("revenue_generated"), 0.0)
        profit_generated = _to_float(m.get("profit_generated"), 0.0)
        store_avg_margin = _to_float(m.get("store_avg_margin"), 0.0)
        return {
            "headline": (
                f"{product_name} is your 2nd best seller but one of your worst profit contributors - {units_sold} units sold, "
                f"${profit_generated:.2f} actual profit"
            ),
            "context": (
                f"Revenue is vanity. Profit is sanity. {product_name} looks strong on your dashboard because it sells, but at "
                f"{estimated_margin*100:.1f}% margin versus your store average of {store_avg_margin*100:.1f}%, every sale of this product is "
                "consuming marketing budget, fulfillment capacity, and customer service resources that could be directed at higher-margin products."
            ),
            "playbook": [
                "Raise the price by 15% and monitor conversion rate for 14 days. If conversion drops less than 15%, you've just improved your margin without losing meaningful revenue. Most store owners underestimate how inelastic demand is for products customers already want.",
                f"Bundle {product_name} with a high-margin product at a combined price that improves your blended margin. The low-margin product drives the sale, the high-margin product improves the economics.",
                f"Reduce ad spend on {product_name} and redirect it to your highest-margin products. Let {product_name} sell organically while you optimize ad ROI on better-margin SKUs.",
                f"Negotiate with your supplier. At {units_sold} units in this period, you have volume leverage. A 5% reduction in COGS on {product_name} could meaningfully improve your margin without changing anything else.",
            ],
            "benchmark": (
                "Healthy Shopify store margins by category average 40-60% for apparel, 30-50% for home goods, 50-70% for digital accessories. "
                "Anything below 20% gross margin is typically unsustainable once you factor in ads, returns, and fulfillment."
            ),
            "urgency": (
                f"You sold {units_sold} units of {product_name} this period and generated ${revenue_generated:.2f} in revenue but only "
                f"${profit_generated:.2f} in profit. If that same effort had gone into your highest-margin product, you would have generated "
                f"approximately ${revenue_generated * store_avg_margin:.2f} in profit instead."
            ),
        }

    return {
        "headline": "Revenue leak detected - action required now",
        "context": "This issue is reducing your store's performance and should be addressed with a concrete 7-day execution plan.",
        "playbook": [
            "Identify the exact metric breakdown for this issue.",
            "Apply a focused intervention for 7 days and monitor movement daily.",
            "Keep what works, remove what does not, and re-test quickly.",
        ],
        "benchmark": "Top-performing Shopify stores run weekly optimization cycles tied to one measurable KPI per intervention.",
        "urgency": "Delaying action keeps the loss compounding while competitors improve faster.",
    }


def test_advice_engine() -> None:
    samples = {
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
            "avg_return_rate_healthy": 0.05,
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
        "low_margin_products_selling_high": {
            "product_name": "Everyday Tee",
            "units_sold": 920,
            "estimated_margin": 0.17,
            "revenue_generated": 22080.0,
            "profit_generated": 3753.60,
            "store_avg_margin": 0.41,
        },
    }

    for action, action_metrics in samples.items():
        print(f"\n=== {action} ===")
        advice = get_action_advice(action, action_metrics)
        print(f"headline: {advice.get('headline')}")
        print(f"context: {advice.get('context')}")
        print("playbook:")
        for step in advice.get("playbook", []):
            print(f" - {step}")
        print(f"benchmark: {advice.get('benchmark')}")
        print(f"urgency: {advice.get('urgency')}")


if __name__ == "__main__":
    test_advice_engine()
