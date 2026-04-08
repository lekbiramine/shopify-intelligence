from config.logging_config import get_logger

logger = get_logger(__name__)

SEVERITY_ICON = {
    "high": "[HIGH]",
    "medium": "[MEDIUM]",
    "low": "[LOW]",
}


def format_currency(value) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


def format_percent(value) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "0.0%"


def _customer_display_name(c: dict) -> str:
    first = (c.get("first_name") or "").strip()
    last = (c.get("last_name") or "").strip()
    name = " ".join(p for p in (first, last) if p)
    if name:
        return name
    cid = c.get("customer_id")
    if cid is not None:
        return f"Customer #{cid}"
    return "Unknown customer"


def _customer_display_email(c: dict) -> str:
    email = (c.get("email") or "").strip()
    return email if email else "no email on file"


def _churned_last_order_phrase(c: dict) -> str:
    days = c.get("days_since_last_order")
    if days is None:
        return "Never ordered"
    return f"Last order: {round(days)} days ago"


def format_insights_section(insights: list[dict]) -> str:
    lines = []

    lines.append("=" * 50)
    lines.append("ACTION REQUIRED - INSIGHTS")
    lines.append("=" * 50)

    if not insights:
        lines.append("\nNo critical insights detected. Store looks healthy.")
        return "\n".join(lines)

    for i, insight in enumerate(insights, start=1):
        icon = SEVERITY_ICON.get(insight["severity"], "[INFO]")
        lines.append(f"\n{icon} {insight['title']}")
        lines.append(f"   Problem : {insight['problem']}")
        lines.append(f"   Impact  : {insight['impact']}")
        lines.append(f"   Action  : {insight['action']}")

    return "\n".join(lines)


def format_inventory_section(data: dict) -> str:
    lines = []

    lines.append("=" * 50)
    lines.append("INVENTORY ALERTS")
    lines.append("=" * 50)

    out_of_stock = data.get("out_of_stock", [])
    lines.append(f"\nOUT OF STOCK ({len(out_of_stock)} variants)")
    if out_of_stock:
        for item in out_of_stock:
            lines.append(
                f"  - {item['product_title']} - {item['variant_title']} "
                f"| SKU: {item['sku'] or 'N/A'} | Available: {item['total_available']}"
            )
    else:
        lines.append("  No out of stock variants.")

    critical = data.get("critical_stock", [])
    lines.append(f"\nCRITICAL STOCK ({len(critical)} variants)")
    if critical:
        for item in critical:
            lines.append(
                f"  - {item['product_title']} - {item['variant_title']} "
                f"| SKU: {item['sku'] or 'N/A'} | Available: {item['total_available']}"
            )
    else:
        lines.append("  No critical stock variants.")

    low = data.get("low_stock", [])
    lines.append(f"\nLOW STOCK ({len(low)} variants)")
    if low:
        for item in low:
            lines.append(
                f"  - {item['product_title']} - {item['variant_title']} "
                f"| SKU: {item['sku'] or 'N/A'} | Available: {item['total_available']}"
            )
    else:
        lines.append("  No low stock variants.")

    return "\n".join(lines)


def format_customers_section(data: dict) -> str:
    lines = []

    lines.append("=" * 50)
    lines.append("CUSTOMER INSIGHTS")
    lines.append("=" * 50)

    churned = data.get("churned", [])
    lines.append(f"\nCHURNED CUSTOMERS ({len(churned)})")
    if churned:
        for c in churned[:10]:
            name = _customer_display_name(c)
            email = _customer_display_email(c)
            lines.append(
                f"  - {name} | {email} | {_churned_last_order_phrase(c)} "
                f"| Spent: {format_currency(c['total_spent'])}"
            )
        if len(churned) > 10:
            lines.append(f"  ... and {len(churned) - 10} more.")
    else:
        lines.append("  No churned customers.")

    never_returned = data.get("never_returned", [])
    lines.append(f"\nONE-TIME CUSTOMERS ({len(never_returned)})")
    if never_returned:
        for c in never_returned[:10]:
            name = _customer_display_name(c)
            email = _customer_display_email(c)
            lines.append(
                f"  - {name} | {email} | Spent: {format_currency(c['total_spent'])}"
            )
        if len(never_returned) > 10:
            lines.append(f"  ... and {len(never_returned) - 10} more.")
    else:
        lines.append("  No one-time customers found.")

    loyal = data.get("loyal", [])
    lines.append(f"\nLOYAL CUSTOMERS ({len(loyal)})")
    if loyal:
        for c in loyal[:10]:
            name = _customer_display_name(c)
            email = _customer_display_email(c)
            lines.append(
                f"  - {name} | {email} "
                f"| Orders: {c['orders_count']} | Spent: {format_currency(c['total_spent'])}"
            )
        if len(loyal) > 10:
            lines.append(f"  ... and {len(loyal) - 10} more.")
    else:
        lines.append("  No loyal customers yet.")

    return "\n".join(lines)


def format_revenue_section(data: dict) -> str:
    lines = []

    lines.append("=" * 50)
    lines.append("REVENUE SUMMARY")
    lines.append("=" * 50)

    summary = data.get("summary", {})
    lines.append(f"\n  Total Orders:       {summary.get('total_orders', 0)}")
    lines.append(f"  Unique Customers:   {summary.get('unique_customers', 0)}")
    lines.append(f"  Gross Revenue:      {format_currency(summary.get('gross_revenue', 0))}")
    lines.append(f"  Total Discounts:    {format_currency(summary.get('total_discounts', 0))}")
    lines.append(f"  Net Revenue:        {format_currency(summary.get('net_revenue', 0))}")
    lines.append(f"  Avg Order Value:    {format_currency(summary.get('avg_order_value', 0))}")

    high_return = data.get("high_return_rate", [])
    lines.append(f"\nHIGH RETURN RATE PRODUCTS ({len(high_return)})")
    if high_return:
        for p in high_return:
            lines.append(
                f"  - {p['product_title']} | Sold: {p['total_sold']} "
                f"| Returned: {p['total_returned']} "
                f"| Rate: {format_percent(p['return_rate'])}"
            )
    else:
        lines.append("  No high return rate products.")

    return "\n".join(lines)


def format_anomalies_section(data: dict) -> str:
    lines = []

    lines.append("=" * 50)
    lines.append("ANOMALIES DETECTED")
    lines.append("=" * 50)

    duplicates = data.get("duplicate_orders", [])
    lines.append(f"\nDUPLICATE ORDERS ({len(duplicates)})")
    if duplicates:
        for d in duplicates:
            lines.append(
                f"  - Customer {d['customer_id']} | Date: {d['order_date']} "
                f"| Amount: {format_currency(d['total_price'])} | Count: {d['order_count']}"
            )
    else:
        lines.append("  No duplicate orders detected.")

    zero_value = data.get("zero_value_orders", [])
    lines.append(f"\nZERO VALUE PAID ORDERS ({len(zero_value)})")
    if zero_value:
        for o in zero_value:
            lines.append(
                f"  - Order {o['order_id']} | {o['email']} "
                f"| Amount: {format_currency(o['total_price'])}"
            )
    else:
        lines.append("  No zero value orders.")

    abnormal = data.get("abnormal_discounts", [])
    lines.append(f"\nABNORMAL DISCOUNTS ({len(abnormal)})")
    if abnormal:
        for o in abnormal:
            lines.append(
                f"  - Order {o['order_id']} | {o['email']} "
                f"| Discount: {o['discount_pct']}%"
            )
    else:
        lines.append("  No abnormal discounts.")

    no_sales = data.get("no_sales_products", [])
    lines.append(f"\nACTIVE PRODUCTS WITH NO SALES ({len(no_sales)})")
    if no_sales:
        for p in no_sales:
            lines.append(f"  - {p['product_title']} | Vendor: {p['vendor']}")
    else:
        lines.append("  All active products have sales.")

    return "\n".join(lines)


def format_full_report(summary: dict) -> str:
    logger.info("Formatting full report...")

    sections = [
        format_insights_section(summary.get("insights", [])),
        format_inventory_section(summary.get("inventory", {})),
        format_customers_section(summary.get("customers", {})),
        format_revenue_section(summary.get("revenue", {})),
        format_anomalies_section(summary.get("anomalies", {})),
    ]

    report = "\n\n".join(sections)
    logger.info("Report formatted successfully.")
    return report