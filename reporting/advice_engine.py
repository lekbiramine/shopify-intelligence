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

    if normalized_type == "duplicate_orders":
        customer_id = _to_str(m.get("customer_id_display"), "").strip()
        dup_n = max(_to_int(m.get("duplicate_order_entries"), 0), 0)
        exposure = _to_float(m.get("duplicate_charge_exposure"), 0.0)
        label = customer_id if customer_id else "a customer"
        return {
            "headline": (
                f"Possible duplicate billing for Customer {customer_id}: {dup_n} same-day identical-total charges"
                if customer_id
                else f"{dup_n} orders look like duplicate charges at the same amount"
            ),
            "context": (
                "When two captures share the same day, customer, and tender amount, fulfillment and support costs double "
                "while trust drops. Payment processors also flag unusually high reversal volume when duplicates sit unresolved."
                + (
                    f" Estimated exposure flagged for this cohort: ${exposure:,.2f}."
                    if exposure > 0
                    else ""
                )
            ),
            "playbook": [
                (
                    f"Open Shopify admin → Orders and filter by Customer ID {customer_id}, same calendar day."
                    if customer_id
                    else "Shopify Admin → Orders: filter by duplicated customer/date and duplicate total."
                ),
                "Refund the duplicate authorization immediately unless both fulfillments intentionally shipped.",
                "Call or email the customer with a concise apology plus proof of reversal to prevent chargebacks.",
                "Add an internal rule: nightly job that flags duplicates by (customer_id, day, gross total) auto-holds fulfillment.",
            ],
            "benchmark": (
                "Card networks penalize merchants with elevated duplicate‑capture disputes; proactive refunds usually cost less than retrieval fees."
            ),
            "urgency": (
                f"Customer {label} sees two charges on their statement tonight. Acting before they dispute preserves processing health."
                if dup_n >= 2
                else "Verify both charges intentionally before issuing any refund."
            ),
        }

    if normalized_type == "revenue_concentration":
        pct = _to_float(m.get("concentration_pct"), 0.0)
        top2_rev = _to_float(m.get("top_two_revenue_share"), 0.0)
        pool = _to_float(m.get("loyal_revenue_pool"), 0.0)
        return {
            "headline": f"Too much loyal-club revenue depends on too few shoppers ({pct:.1f}% in your top‑2 cohort)",
            "context": (
                f"${top2_rev:,.2f} of roughly ${pool:,.2f} monitored loyal-club revenue is concentrated in two accounts. "
                "If either pauses unexpectedly, forecasting and cash planning swing hard with little warning."
            ),
            "playbook": [
                "Identify the fifth-through-tenth ranked loyal purchasers and activate a repeatable second-order offer this week.",
                "Launch a SKU bundling ladder so large buyers naturally recruit mid-tier purchasers into higher frequency.",
                "Document a lightweight VIP diversification metric (top‑N share %) and publish it beside weekly revenue summaries.",
                "Shift paid remarketing budgets toward cohorts resembling your tier‑2 shoppers until concentration trends down.",
            ],
            "benchmark": "Sophisticated Shopify Plus operators usually keep flagship loyal revenue below ~35% attributable to two individuals.",
            "urgency": (
                "Concentrated revenue is benign until one buyer churns silently—then forecasting confidence collapses overnight."
            ),
        }

    if normalized_type == "abnormal_discount":
        order_hint = _to_str(m.get("order_id_hint"), "").strip()
        disc = _to_float(m.get("discount_pct_hint"), 0.0)
        leak = _to_float(m.get("estimated_leak_usd"), 0.0)
        return {
            "headline": (
                f"Order {order_hint or 'detected'} has an extreme {disc:.1f}% discount — reconcile before more ship"
                if disc > 0
                else "Order-level discount anomaly detected — validate before fulfilment ramps"
            ),
            "context": (
                "Stacked automatic discounts can silently torch margin on trending SKUs."
                + (f" Flagged bleed this period ≈ ${leak:.2f}." if leak > 0 else "")
            ),
            "playbook": [
                (
                    f"Locate order {order_hint} → Discounts pane and screenshot every applied rule."
                    if order_hint
                    else "Search recent high-discount orders in Admin and capture each discount stack trace."
                ),
                "Disable overlapping scripts or Shopify Functions until the stack reproduces cleanly in draft checkout.",
                "Issue a corrective partial capture or goodwill credit only after finance signs the reversal.",
                "Add a Shopify Flow pause when effective discount_pct > configured guardrail.",
            ],
            "benchmark": "Operational teams benchmarking DTC storefronts intervene when single-order discounts eclipse 60% unless part of audited clearance flows.",
            "urgency": "Every duplicated shipment multiplies reversible COGS—the earlier you freeze picking, the cheaper the remediation.",
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

    if normalized_type == "discount_overuse":
        discount_rate = max(_to_float(m.get("discount_rate"), 0.0), 0.0)
        discounted_orders = _to_int(m.get("discounted_orders"), 0)
        total_orders = _to_int(m.get("total_orders"), 0)
        total_discount_given = _to_float(m.get("total_discount_given"), 0.0)
        avg_discount_amount = _to_float(m.get("avg_discount_amount"), 0.0)
        most_used_code = _to_str(m.get("most_used_code"), "your top discount code")
        raw_store_aov = _to_float(m.get("store_aov"), 0.0)
        store_aov = raw_store_aov if raw_store_aov > 0 else 35.00
        return {
            "headline": (
                f"{discount_rate * 100:.1f}% of your orders used a "
                "discount code — you trained your customers to "
                "never pay full price"
            ),
            "context": (
                f"You gave away ${total_discount_given:.2f} in discounts "
                "this month alone. Hormozi's core pricing principle: "
                "every time you discount, you teach your customer that "
                f"your full price is a lie. At {discount_rate * 100:.1f}% "
                f"discount rate, {discounted_orders} out of your last "
                f"{total_orders} customers paid less than your product "
                "is worth. This compounds — next month that rate will "
                "be higher unless you act."
            ),
            "playbook": [
                (
                    f"Retire '{most_used_code}' immediately. Replace it "
                    "with a value-based offer: free shipping on orders "
                    "over $X, a free gift with purchase, or early access "
                    "to new products. Same perceived value, zero margin "
                    "destruction."
                ),
                (
                    "Introduce a loyalty program instead of open discounts. "
                    "'Buy 3 times, get 15% off forever' is a reward for "
                    "loyalty. A public discount code is a reward for "
                    "being a first-time buyer who found a coupon site."
                ),
                (
                    f"Email your {discounted_orders} discount buyers "
                    "personally. Tell them you're retiring the code but "
                    "they're getting something better — a loyalty reward "
                    "or exclusive access. Most will stay. The ones who "
                    "leave only came for the discount anyway."
                ),
                (
                    "Run a 30-day no-discount experiment on your top "
                    "product. Raise the price by the average discount "
                    f"amount (${avg_discount_amount:.2f}) and see if "
                    "conversion drops more than 15%. If not, you've "
                    "permanently recovered that margin."
                ),
            ],
            "benchmark": (
                "Shopify stores with discount rates above 30% "
                "average 40% lower customer LTV compared to stores "
                "that use value-based offers. Discount addiction is "
                "the #1 silent margin killer in e-commerce."
            ),
            "urgency": (
                f"At your current discount rate, you will give away "
                f"${total_discount_given * 12:.2f} in discounts over "
                "the next 12 months. That money could fund "
                f"{_safe_int_div(total_discount_given * 12, store_aov, 0):.0f} "
                "new customer acquisitions instead."
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

    if normalized_type == "no_post_purchase_upsell":
        total_orders = _to_int(m.get("total_orders"), 0)
        avg_items_per_order = _to_float(m.get("avg_items_per_order"), 0.0)
        store_aov = _to_float(m.get("store_aov"), 0.0) or 35.00
        monthly_revenue = _to_float(m.get("monthly_revenue"), 0.0)
        upsell_opportunity = _to_float(m.get("upsell_opportunity"), monthly_revenue * 0.15)
        return {
            "headline": (
                f"You're leaving ${upsell_opportunity:.0f}/month on the table — "
                "every customer buys once and leaves"
            ),
            "context": (
                f"Your store processes {total_orders} orders per month with an average of "
                f"{avg_items_per_order:.1f} items per order. Industry data shows post-purchase upsells convert "
                "at 8-15% with zero additional acquisition cost — the customer already bought, trust is at its peak, "
                "payment details are saved. A 10% AOV increase on your current revenue generates the same result as a "
                "10% traffic increase but costs nothing in ad spend. Hormozi principle: the best time to sell is "
                "immediately after the first sale."
            ),
            "playbook": [
                (
                    "Install a post-purchase upsell app (ReConvert or AfterSell) and create one offer: your best-selling "
                    "product at 15% off, shown immediately after checkout. Target: customers who just bought your top "
                    "product. Expected acceptance rate: 8-15%."
                ),
                (
                    f"Set your free shipping threshold 20% above your current AOV of ${store_aov:.2f} — so at "
                    f"${store_aov * 1.20:.2f}. Add a progress bar in the cart. Customers will add items to hit the "
                    "threshold. This alone increases AOV by 12-18% on average."
                ),
                (
                    "Add 'frequently bought together' bundles on your top 3 product pages. Amazon reports 35% of "
                    "revenue comes from recommendations. You don't need their algorithm — just manually pair what goes "
                    "together."
                ),
                (
                    "Send a post-purchase email sequence: Day 1 (how to use your product), Day 3 (related product "
                    "recommendation at 10% off), Day 14 (replenishment reminder if consumable). Klaviyo data: "
                    "post-purchase flows generate 30x more revenue per recipient than broadcast campaigns."
                ),
            ],
            "benchmark": (
                "Shopify stores with active post-purchase upsell strategies generate 8-15% of total revenue from upsells "
                "alone. A store doing $50k/month that implements upsells correctly adds $4,000-$7,500/month with zero "
                "additional ad spend. Post-purchase upsells convert at 8-15% because the buying decision is already made. "
                "(ReConvert 2024 Benchmark Report)"
            ),
            "urgency": (
                f"Every month without a post-purchase strategy is ${upsell_opportunity:.2f} in recoverable revenue that "
                f"goes to zero. At {total_orders} orders/month, even a 10% upsell acceptance rate at "
                f"${store_aov * 0.20:.2f} average upsell value adds "
                f"${total_orders * 0.10 * store_aov * 0.20:.2f}/month with no new traffic required."
            ),
        }

    if normalized_type == "no_email_automation_flows":
        total_customers = _to_int(m.get("total_customers"), 0)
        one_time_buyers = _to_int(m.get("one_time_buyers"), 0)
        repeat_rate = max(_to_float(m.get("repeat_rate"), 0.0), 0.0)
        store_aov = _to_float(m.get("store_aov"), 0.0) or 35.00
        winback_opportunity = _to_float(m.get("winback_opportunity"), one_time_buyers * store_aov * 0.08)
        return {
            "headline": (
                f"{one_time_buyers} customers bought once and disappeared — "
                f"${winback_opportunity:.2f} in recoverable revenue sitting in your list"
            ),
            "context": (
                "Klaviyo's 2026 benchmark data across 183,000 stores confirms: email flows generate 41% of total email "
                f"revenue from just 5.3% of sends, with revenue per recipient 18x higher than broadcast campaigns. Your "
                f"{one_time_buyers} one-time buyers already trust you enough to have bought once. An automated win-back flow "
                "costs nothing to run after setup and works 24/7. Most stores don't have one. This is the highest-ROI "
                "marketing asset you're not using."
            ),
            "playbook": [
                (
                    "Build a 3-email abandoned cart flow: Email 1 at 1 hour (no discount, just a direct link back), "
                    "Email 2 at 24 hours (10% discount, 48hr expiry), Email 3 at 72 hours (last chance + social proof). "
                    "Klaviyo benchmark: abandoned cart flows convert at 15-20%. Every week without this flow costs you "
                    "recoverable revenue."
                ),
                (
                    f"Build a win-back flow for {one_time_buyers} customers who haven't ordered in 60+ days: "
                    "Email 1 at day 60 (soft check-in), Email 2 at day 75 (specific offer tied to last product "
                    "purchased), Email 3 at day 90 (last chance). Stop the sequence the moment they buy."
                ),
                (
                    "Build a post-purchase flow: Email 1 immediately (order confirmation + what to expect), Email 2 "
                    "at day 3 (how to get the most out of their purchase), Email 2 at day 14 (related product "
                    "recommendation). This alone lifts repeat purchase rate by 8-15%."
                ),
                (
                    "Build a welcome series for new subscribers: Email 1 immediately (brand story + best seller), "
                    "Email 2 at day 2 (social proof + reviews), Email 3 at day 5 (10% first purchase offer). "
                    "Welcome series convert at 8-12% — highest conversion of any email flow."
                ),
            ],
            "benchmark": (
                "Klaviyo 2026 data: automated email flows generate nearly 41% of total email revenue from just 5.3% of "
                "sends. Welcome series achieve 45-50% open rates. Abandoned cart flows achieve 35-40% open rates with "
                "15-20% conversion. Win-back flows achieve 25-30% open rates with 5-8% reactivation rate. The median "
                "Shopify store has zero of these flows active."
            ),
            "urgency": (
                "Every day without automated flows is revenue leaking silently. Your "
                f"{one_time_buyers} one-time buyers are reachable right now. At an 8% reactivation rate and "
                f"${store_aov:.2f} AOV, a win-back flow generates "
                f"${one_time_buyers * 0.08 * store_aov:.2f} in recovered revenue — running automatically, forever, "
                "at zero marginal cost."
            ),
        }

    if normalized_type == "low_aov_no_bundle_strategy":
        store_aov = _to_float(m.get("store_aov"), 0.0) or 35.00
        total_orders = _to_int(m.get("total_orders"), 0)
        monthly_revenue = _to_float(m.get("monthly_revenue"), 0.0)
        bundle_opportunity = _to_float(m.get("bundle_opportunity"), monthly_revenue * 0.20)
        return {
            "headline": (
                f"Your AOV is ${store_aov:.2f} — industry average is $85. "
                f"Closing that gap adds ${bundle_opportunity:.2f} per month with zero new customers"
            ),
            "context": (
                "Average order value is one of three revenue levers (traffic, conversion, AOV). It is the only one you "
                f"can improve without spending on ads. Your current AOV of ${store_aov:.2f} means every customer is "
                "buying the minimum. Implementing bundling, free shipping thresholds, and upsells typically lifts AOV by "
                f"20-30% within 60 days. A 20% AOV increase on ${monthly_revenue:.2f} monthly revenue = "
                f"${monthly_revenue * 0.20:.2f}/month in additional revenue. No new traffic. No new ads. "
                "Hormozi: volume times price times conversion — if you improve price (AOV), everything else multiplies."
            ),
            "playbook": [
                (
                    "Create 3 product bundles from your existing catalog. Pair your #1 product with your #3 product at "
                    f"10% combined discount. Price it so the bundle AOV is ${store_aov * 1.35:.2f}+. Bundles increase "
                    "AOV by 15-25% and move slower inventory."
                ),
                (
                    f"Set a free shipping threshold at ${store_aov * 1.20:.2f} (20% above your current AOV of "
                    f"${store_aov:.2f}). Add a cart progress bar showing how close customers are. 72% of shoppers say "
                    "free shipping influences purchase decisions."
                ),
                (
                    "Add quantity discounts: buy 2 save 10%, buy 3 save 15%. This increases units per order and AOV "
                    "simultaneously. Works especially well for consumables, apparel, and home goods."
                ),
                (
                    "Raise prices on your top 3 products by 10-15% and monitor conversion for 14 days. Most store owners "
                    "underestimate price elasticity. If conversion drops less than 10%, you've permanently increased AOV. "
                    "Hormozi: most businesses are undercharging by 20-30% and don't know it."
                ),
            ],
            "benchmark": (
                "Industry benchmarks: implementing free shipping threshold + bundles + upsells simultaneously increases "
                "AOV by 20-40% within 60 days. A 10% AOV increase generates the same revenue as a 10% traffic increase "
                "at zero ad cost. US ecommerce average AOV is $85-100. Fashion averages $50-80, home goods $100-200. "
                "(Shopify 2024, EasyApps 2026)"
            ),
            "urgency": (
                f"At {total_orders} orders/month, every $1 increase in AOV = ${total_orders:.0f} in monthly revenue. "
                f"Closing even half the gap between your current ${store_aov:.2f} and the $85 industry average = "
                f"${total_orders * ((85 - store_aov) / 2):.2f}/month in additional revenue. Every month at current AOV "
                "is that money gone."
            ),
        }

    if normalized_type == "single_product_revenue_concentration":
        top_product_name = _to_str(m.get("top_product_name"), "Your top product")
        top_product_revenue_share = max(_to_float(m.get("top_product_revenue_share"), 0.0), 0.0)
        top_product_revenue = _to_float(m.get("top_product_revenue"), 0.0)
        total_revenue = _to_float(m.get("total_revenue"), 0.0)
        store_aov = _to_float(m.get("store_aov"), 0.0) or 35.00
        return {
            "headline": (
                f"{top_product_name} generates {top_product_revenue_share * 100:.1f}% of your revenue — "
                "one bad month destroys your business"
            ),
            "context": (
                f"${top_product_revenue:.2f} of your ${total_revenue:.2f} in revenue comes from one product. This is "
                f"concentration risk — the same problem that kills investor portfolios kills ecommerce stores. If "
                f"{top_product_name} gets a bad review, a supply disruption, a copycat competitor, or a Facebook ad policy "
                f"change, your entire revenue collapses. The most resilient stores have no single product above 30% of "
                f"revenue. You are at {top_product_revenue_share * 100:.1f}%."
            ),
            "playbook": [
                (
                    f"Identify your #2 and #3 selling products and run a dedicated campaign for each this month. "
                    f"The goal is not to hurt {top_product_name} — it's to build revenue underneath it so a single "
                    "failure doesn't collapse everything."
                ),
                (
                    f"Bundle {top_product_name} with 2 other products from your catalog. This cross-sells existing "
                    "inventory, increases AOV, and moves revenue to a multi-product transaction instead of a "
                    "single-product one."
                ),
                (
                    "Launch one new product this quarter specifically to diversify your revenue base. It doesn't need "
                    "to be a bestseller — it needs to work. Even 10% of revenue from a new product reduces your "
                    "concentration risk significantly."
                ),
                (
                    f"Run ads specifically for your non-{top_product_name} products. Even if ROAS is slightly lower, "
                    "you're buying insurance against concentration collapse."
                ),
            ],
            "benchmark": (
                "Shopify merchants with single-product concentration above 50% are 3x more likely to see revenue drops of "
                "30%+ when that product faces competition, reviews, or supply issues. Diversified stores (no product above "
                "30% of revenue) show 40% more stable month-over-month revenue. (Shopify Merchant Research 2024)"
            ),
            "urgency": (
                f"Right now, {top_product_revenue_share * 100:.1f}% of your revenue depends on one product performing "
                f"perfectly. A single 1-star review campaign, a competitor price drop, or an ad account suspension costs you "
                f"${top_product_revenue:.2f}/month immediately. This risk costs nothing to reduce — it only requires "
                "intentional action this month."
            ),
        }

    if normalized_type == "no_subscription_revenue":
        repeat_rate = max(_to_float(m.get("repeat_rate"), 0.0), 0.0)
        total_repeat_orders = _to_int(m.get("total_repeat_orders"), 0)
        store_aov = _to_float(m.get("store_aov"), 0.0) or 35.00
        monthly_revenue = _to_float(m.get("monthly_revenue"), 0.0)
        subscription_opportunity = _to_float(m.get("subscription_opportunity"), monthly_revenue * 0.25)
        return {
            "headline": (
                f"{repeat_rate * 100:.1f}% of your customers reorder the same product — "
                "they want a subscription and you're not offering one"
            ),
            "context": (
                f"You have {total_repeat_orders} repeat orders on the same SKUs — customers literally coming back to "
                "rebuy the same thing manually. This is the clearest signal that subscription revenue is available to you. "
                "Subscription customers have 3-5x higher lifetime value than one-time buyers. They generate predictable, "
                "compounding monthly revenue. And crucially — they don't need to be re-acquired with ad spend every cycle. "
                "Hormozi principle: the best business model is one where the customer has to actively cancel to stop paying you."
            ),
            "playbook": [
                (
                    "Install a Shopify subscription app (Recharge or Loop Subscriptions) and offer 'Subscribe and Save 15%' "
                    "on your top 3 repeat-purchase products. Setup takes one day. Revenue compounds monthly."
                ),
                (
                    f"Email your {total_repeat_orders} repeat buyers personally: 'We noticed you reorder [product] "
                    "regularly. Subscribe and save 15% — cancel anytime.' This segment converts at 20-30% because they "
                    "already proved they want it."
                ),
                (
                    "Set the default subscription interval to match your product's natural consumption cycle. If customers "
                    "reorder every 35 days on average, offer monthly (30-day) subscriptions. Alignment with behavior "
                    "maximizes retention."
                ),
                (
                    "Offer a subscriber-exclusive benefit: early access to new products, a free sample with every box, "
                    "or priority customer service. Make subscription feel like a VIP tier, not just autopay."
                ),
            ],
            "benchmark": (
                "Subscription ecommerce grew 68% in 2024. Subscription customers have 3-5x higher LTV than one-time buyers. "
                "Average subscription retention rate is 85% month-over-month. A store converting 20% of repeat buyers to "
                "subscribers generates predictable recurring revenue that doesn't require re-acquisition. "
                "(Recharge 2024 State of Subscription Commerce)"
            ),
            "urgency": (
                f"Every month without a subscription offering, your {total_repeat_orders} repeat buyers manually reorder — "
                "and there is a chance they forget, find a competitor, or simply churn. Converting even 20% of them to "
                f"subscribers at ${store_aov:.2f}/month locks in "
                f"${total_repeat_orders * 0.20 * store_aov:.2f} in predictable monthly revenue. Starting now means "
                "compounding starts now."
            ),
        }

    if normalized_type == "high_single_order_customer_ratio":
        one_time_buyers = _to_int(m.get("one_time_buyers"), 0)
        total_customers = _to_int(m.get("total_customers"), 0)
        one_time_ratio = max(_to_float(m.get("one_time_ratio"), 0.0), 0.0)
        store_aov = _to_float(m.get("store_aov"), 0.0) or 35.00
        ltv_gap = _to_float(m.get("ltv_gap"), store_aov * 3.0)
        actual_avg_ltv = _to_float(m.get("actual_avg_ltv"), 0.0)
        return {
            "headline": (
                f"{one_time_ratio * 100:.1f}% of your customers bought once and never came back — "
                "you're running an acquisition treadmill"
            ),
            "context": (
                f"Out of {total_customers} total customers, {one_time_buyers} bought exactly once. You paid to acquire "
                "them, they bought, they left. This is the acquisition treadmill — the most expensive and exhausting way "
                "to run an ecommerce business. Every month you need the same ad budget just to stay flat. Hormozi's core "
                "principle: the real money in business is in the back end, not the front end. Your back end is not working. "
                "Fixing retention by 10% is worth more than increasing acquisition by 30%."
            ),
            "playbook": [
                (
                    "Implement a post-purchase email sequence for every new buyer starting today: Day 1 (thank you + usage "
                    "tips), Day 14 (related product at 10% off), Day 30 (loyalty check-in + reward). This alone lifts repeat "
                    "purchase rate by 8-15%."
                ),
                (
                    "Create a loyalty program with a simple mechanic: after 3 purchases, customers get 15% off forever. "
                    "No app required — a manual discount code sent after purchase 3 works. The goal is to make the 3rd "
                    "purchase feel rewarded."
                ),
                (
                    f"Segment your {one_time_buyers} single buyers by what they purchased and send a targeted reorder "
                    "campaign this week. One sentence: 'Running low on [product]? Reorder at 10% off — today only.' "
                    "Urgency + relevance = conversion."
                ),
                (
                    "Find out why they didn't come back. Send a 2-question survey to 100 random one-time buyers: "
                    "'What stopped you from ordering again?' The answers will tell you more than any analytics dashboard. "
                    "Hormozi: the customer who tells you why they left is your most valuable customer."
                ),
            ],
            "benchmark": (
                "Increasing customer retention by just 5% increases profits by 25-95% (Bain & Company). Acquiring a new "
                "customer costs 5-7x more than retaining an existing one. Shopify stores with repeat purchase rates above "
                f"27% generate 3x the LTV per customer compared to stores below 15%. Your goal: move from "
                f"{one_time_ratio * 100:.1f}% one-time buyers to below 60%."
            ),
            "urgency": (
                f"You have {one_time_buyers} customers who already trust you enough to have bought once. Getting just 10% "
                f"of them to buy again at ${store_aov:.2f} AOV = ${one_time_buyers * 0.10 * store_aov:.2f} in revenue "
                "that requires zero ad spend. Every day without a retention strategy is that money sitting uncollected."
            ),
        }

    if normalized_type == "pricing_below_market":
        avg_product_price = _to_float(m.get("avg_product_price"), 0.0)
        low_price_revenue_share = max(_to_float(m.get("low_price_revenue_share"), 0.0), 0.0)
        store_aov = _to_float(m.get("store_aov"), 0.0) or 35.00
        total_revenue = _to_float(m.get("total_revenue"), 0.0)
        price_increase_opportunity = _to_float(m.get("price_increase_opportunity"), total_revenue * 0.15)
        return {
            "headline": (
                f"Your average product price is ${avg_product_price:.2f} — you may be undercharging by 15-25% "
                "and not knowing it"
            ),
            "context": (
                "Most store owners set prices based on gut feeling and competitor copying — then never raise them. "
                "Hormozi's pricing principle: price is a signal of value. Low prices don't attract better customers — "
                "they attract price-sensitive customers who churn the moment a competitor offers 10% less. At your "
                f"current pricing, a 15% price increase across your catalog adds ${price_increase_opportunity:.2f} in "
                "monthly revenue with zero change in traffic, conversion rate, or operations. Most stores see less than "
                "10% conversion drop from a 15% price increase — meaning net revenue goes up."
            ),
            "playbook": [
                (
                    "Pick your #1 selling product and raise the price by 10%. Monitor conversion rate for 14 days. "
                    "If it drops less than 8%, raise another 5%. If it holds, you've permanently increased revenue from "
                    "your best product with no downside."
                ),
                (
                    "Add perceived value to justify higher prices: better product photos, stronger copy, more detailed "
                    "specifications, social proof. Price and perceived value must move together. Upgrade the presentation "
                    "before raising the price."
                ),
                (
                    "Bundle low-price items to increase transaction value. A $12 product is hard to sell profitably. "
                    "Three $12 products bundled at $32 with better margins and better AOV solves the problem without "
                    "changing your catalog."
                ),
                (
                    "Survey 20 recent customers with one question: 'At what price would [product] feel too expensive?' "
                    "Most will name a number 20-40% above what you currently charge. You have more pricing power than you think."
                ),
            ],
            "benchmark": (
                "Hormozi principle: most businesses are undercharging by 20-30% and the market would pay more without "
                "significant conversion impact. Price elasticity research shows a 10% price increase causes less than 10% "
                "conversion drop in 70% of ecommerce categories — net revenue positive in most cases. The exception: pure "
                "commodity products with identical alternatives on the same page."
            ),
            "urgency": (
                f"At ${total_revenue:.2f}/month current revenue, a 15% price increase that causes 10% conversion drop still "
                f"nets ${total_revenue * 0.15 * 0.90:.2f} in additional monthly revenue. Every month at current pricing is "
                f"${price_increase_opportunity * 0.50:.2f} in conservative upside left on the table."
            ),
        }

    if normalized_type == "review_count_too_low":
        total_orders = _to_int(m.get("total_orders"), 0)
        store_aov = _to_float(m.get("store_aov"), 0.0) or 35.00
        monthly_revenue = _to_float(m.get("monthly_revenue"), 0.0)
        review_opportunity = _to_float(m.get("review_opportunity"), monthly_revenue * 0.12)
        return {
            "headline": (
                f"You've fulfilled {total_orders} orders with no systematic review collection — "
                "you're invisible to new buyers"
            ),
            "context": (
                "93% of consumers read reviews before purchasing. Stores with 50+ reviews convert at 4.6% compared to 2.9% "
                f"for stores with under 10 reviews — a 58% conversion lift from reviews alone. You've fulfilled {total_orders} "
                "orders — that's potential reviews sitting uncollected. Every order you don't follow up on for a review is a "
                "conversion opportunity for your next visitor that doesn't exist. Hormozi: social proof is the most efficient "
                "form of marketing because customers do the selling for you."
            ),
            "playbook": [
                (
                    "Send a review request email to every customer 7-10 days after delivery. Subject line: "
                    "'Quick question about your [product].' One sentence body. One link. Review request emails get 5-10x "
                    "more reviews than hoping customers do it organically."
                ),
                (
                    f"Email your top {min(total_orders, 50)} customers from the last 90 days this week asking for a review. "
                    "Offer a $5 store credit in exchange. $5 credit costs less than a new customer acquisition and generates "
                    "social proof that converts forever."
                ),
                (
                    "Install a review app (Judge.me or Loox) and automate post-purchase review requests. One-time setup, "
                    "permanent compounding benefit. Stores with automated review collection average 8x more reviews than "
                    "stores without."
                ),
                (
                    "Display reviews prominently on product pages — above the fold if possible. A product page with visible "
                    "reviews converts 58% better than one without. Reviews are free conversion rate optimization."
                ),
            ],
            "benchmark": (
                "93% of consumers say reviews influence purchase decisions. Products with 50+ reviews have 4.6% conversion "
                "rates vs 2.9% for products with fewer than 10 reviews — a 58% lift. Review emails sent 7-10 days "
                "post-delivery achieve 15-25% response rates. (Spiegel Research Center, BrightLocal 2024)"
            ),
            "urgency": (
                "Every week without review collection is another week where new visitors see empty review sections and leave. "
                f"At {total_orders} orders/month and a 58% conversion lift from reviews, the implied revenue opportunity is "
                f"${review_opportunity:.2f}/month. Every day you wait, a competitor with 200 reviews is winning your "
                "potential customers."
            ),
        }

    if normalized_type == "cart_abandonment_no_recovery":
        abandoned_count = _to_int(m.get("abandoned_count"), 0)
        abandonment_rate = max(_to_float(m.get("abandonment_rate"), 0.0), 0.0)
        store_aov = _to_float(m.get("store_aov"), 0.0) or 35.00
        potential_recovery = _to_float(m.get("potential_recovery"), abandoned_count * store_aov * 0.15)
        weekly_loss = _to_float(m.get("weekly_loss"), abandoned_count * store_aov)
        return {
            "headline": (
                f"{abandoned_count} carts abandoned this week — ${weekly_loss:.2f} left at the door with no recovery system"
            ),
            "context": (
                f"Average ecommerce abandonment rate is 69-70%. Your rate of {abandonment_rate * 100:.1f}% means "
                f"{abandoned_count} people this week added products to their cart, started checkout, and left. These are "
                "your highest-intent visitors — they went further than anyone else. Without an automated recovery sequence, "
                "they are gone forever. Klaviyo data: abandoned cart emails sent within 1 hour recover 3x more revenue than "
                "emails sent at 24 hours. A 3-email sequence recovers 15-20% of abandoned carts on average. You are recovering 0%."
            ),
            "playbook": [
                (
                    f"Send Email 1 within 1 hour of abandonment: no discount, just 'You left something behind' with a direct "
                    f"link back to cart. This alone recovers 5-8% of abandoned carts. At {abandoned_count} weekly abandonments, "
                    f"that's {int(abandoned_count * 0.06)} orders recovered per week at zero cost."
                ),
                (
                    "Send Email 2 at 24 hours: add a 10% discount code with 48-hour expiry. 'Still thinking about it? "
                    "Here's 10% off — expires in 48 hours.' This recovers an additional 4-6% of remaining abandoned carts."
                ),
                (
                    "Send Email 3 at 72 hours: last chance + social proof. 'Your cart expires tonight + [X people bought this "
                    "this week].' Scarcity + social proof = final conversion push."
                ),
                (
                    "Check your checkout on mobile RIGHT NOW. 67% of abandonment spikes are caused by a broken mobile "
                    "experience — a button that doesn't work, a payment method that disappeared, or a form that won't submit. "
                    "This is free to fix and immediate."
                ),
            ],
            "benchmark": (
                "Klaviyo 2026: abandoned cart flows achieve 35-40% open rates and 15-20% conversion rates. A 3-email abandoned "
                "cart sequence recovers 15-20% of abandoned carts on average. Email 1 at 1 hour recovers 3x more than Email 1 "
                "at 24 hours. The average Shopify store without cart recovery loses $4,000-$15,000/month in recoverable revenue."
            ),
            "urgency": (
                f"At {abandoned_count} abandonments/week and ${store_aov:.2f} AOV, a 15% recovery rate = "
                f"${potential_recovery:.2f}/week = ${potential_recovery * 4:.2f}/month in recovered revenue. Every week "
                "without this sequence running is recoverable revenue gone. Setup takes 2 hours. Revenue runs forever."
            ),
        }

    if normalized_type == "no_loyalty_program":
        repeat_rate = max(_to_float(m.get("repeat_rate"), 0.0), 0.0)
        total_customers = _to_int(m.get("total_customers"), 0)
        repeat_buyers = _to_int(m.get("repeat_buyers"), 0)
        store_aov = _to_float(m.get("store_aov"), 0.0) or 35.00
        monthly_revenue = _to_float(m.get("monthly_revenue"), 0.0)
        loyalty_opportunity = _to_float(m.get("loyalty_opportunity"), monthly_revenue * 0.18)
        return {
            "headline": (
                "Your repeat buyers are loyal without a reason — a loyalty program turns habit into commitment"
            ),
            "context": (
                f"{repeat_rate * 100:.1f}% of your customers come back without any incentive to do so. That's {repeat_buyers} "
                "people who like your product enough to return voluntarily. A loyalty program doesn't create loyalty — it "
                "rewards it and makes it sticky. Customers enrolled in loyalty programs spend 67% more per year than "
                "non-members. They refer 3x more new customers. They have 5x lower churn rate. And critically — they feel "
                "stupid buying from a competitor because they'd lose their points. Hormozi: the goal is to make switching "
                "cost higher than the alternative's benefit."
            ),
            "playbook": [
                (
                    "Start with the simplest possible mechanic: 'Buy 5 times, get your next order 20% off — automatically.' "
                    "Email every customer their purchase count. No app required. Manual discount code after purchase 5. "
                    "This is free to implement and starts compounding immediately."
                ),
                (
                    f"Create a VIP tier for your top {min(repeat_buyers, 20)} repeat buyers: exclusive early access to new "
                    "products, a personal thank-you from you, a surprise gift in their next order. Cost: near zero. Impact: "
                    "these customers become brand ambassadors. Hormozi: the best marketing is customers who can't stop talking "
                    "about you."
                ),
                (
                    "Add a referral component: 'Refer a friend, both get 10% off your next order.' Referral programs cost 5x "
                    "less per acquisition than ads and bring higher-quality customers (referred customers have 37% higher "
                    "retention). Setup takes one afternoon."
                ),
                (
                    "Communicate the program through email, not just the website. Send a dedicated 'You're in our loyalty "
                    "program' email to every customer who has made 2+ purchases. Make them feel special before they hit the "
                    "reward threshold."
                ),
            ],
            "benchmark": (
                "Loyalty program members spend 67% more annually than non-members. Programs increase repeat purchase rate by "
                "20-30% on average. Referred customers have 37% higher retention and 16% higher LTV than non-referred "
                "customers. 77% of customers say loyalty programs make them more likely to continue doing business with a brand. "
                "(Bond Brand Loyalty 2024, Nielsen)"
            ),
            "urgency": (
                f"Every month without a loyalty program, your {repeat_buyers} repeat buyers are one bad experience or "
                "competitor offer away from leaving permanently. A loyalty program increases monthly revenue by 15-20% on "
                f"average through higher purchase frequency and higher AOV. At your current ${monthly_revenue:.2f} monthly "
                f"revenue, that's ${loyalty_opportunity:.2f} in recoverable monthly revenue — compounding every month the "
                "program is running."
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
