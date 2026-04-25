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


def _clean_text(value: object, default: str = "Unknown") -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text or text.lower() in {"n/a", "none", "null"}:
        return default
    return text


def _is_meaningful_customer(c: dict) -> bool:
    has_name = bool((c.get("first_name") or "").strip() or (c.get("last_name") or "").strip())
    has_email = bool((c.get("email") or "").strip())
    return has_name or has_email


def _group_inventory(items: list[dict]) -> list[dict]:
    grouped: dict[str, dict] = {}
    for item in items:
        product = _clean_text(item.get("product_title"), "Unnamed Product")
        sku = _clean_text(item.get("sku"), "-")
        key = product
        row = grouped.setdefault(
            key,
            {
                "product_title": product,
                "variants": set(),
                "total_available": 0,
                "sku_count": 0,
                "demand_score": 0,
            },
        )
        row["variants"].add(_clean_text(item.get("variant_title"), "Default"))
        row["total_available"] += int(item.get("total_available") or 0)
        if sku != "-":
            row["sku_count"] += 1
        row["demand_score"] += 1

    result = []
    for row in grouped.values():
        row["variant_label"] = "All variants" if len(row["variants"]) > 1 else next(iter(row["variants"]))
        result.append(row)
    result.sort(key=lambda x: (-x["demand_score"], x["total_available"], x["product_title"]))
    return result


def _with_money_language(text: str, fallback_value: float = 0.0) -> str:
    if "$" in text or "revenue" in text.lower() or "loss" in text.lower() or "opportunity" in text.lower():
        return text
    return f"{text} (~${fallback_value:,.2f} at risk/opportunity)"


def _derive_top_priorities(insights: list[dict]) -> list[dict]:
    def impact_rank(insight: dict) -> int:
        title = (insight.get("title") or "").lower()
        impact_type = (insight.get("impact_type") or "").lower()
        # 1) Revenue loss prevention, 2) Revenue recovery, 3) Growth
        if impact_type == "risk" or "return" in title or "duplicate" in title or "discount" in title:
            return 0
        if "churn" in title or "dead inventory" in title:
            return 1
        return 2

    ranked = sorted(
        insights,
        key=lambda i: (
            {"high": 0, "medium": 1, "low": 2}.get(i.get("severity", "low"), 9),
            impact_rank(i),
            -float(i.get("potential_value", 0) or 0),
        ),
    )
    return ranked[:3]


def _derive_key_issues(insights: list[dict]) -> list[dict]:
    return [i for i in insights if i.get("severity") in {"high", "medium"}][:4]


def _used_titles(priorities: list[dict]) -> set[str]:
    return {str(p.get("title") or "").strip() for p in priorities}


def _remaining_key_issues(insights: list[dict], used_titles: set[str]) -> list[dict]:
    result = []
    for i in insights:
        title = str(i.get("title") or "").strip()
        if title in used_titles:
            continue
        if i.get("severity") not in {"high", "medium"}:
            continue
        result.append(i)
    return result[:4]


def _build_30_min_plan(priorities: list[dict]) -> list[str]:
    plan = []
    for item in priorities:
        title = (item.get("title") or "").lower()
        if "churn" in title:
            plan.append("Recover churned revenue -> send win-back emails (5 min)")
        elif "return" in title:
            plan.append("Fix revenue leakage -> pause high-return SKU (2 min)")
        elif "dead inventory" in title:
            plan.append("Unlock tied capital -> run dead inventory discounts (15 min)")
        elif "concentration" in title:
            plan.append("Reduce dependency risk -> run new-customer campaign (8 min)")
    if not plan:
        plan = ["Review top issue and execute first action (10 min)"]
    return plan[:3]


def format_insights_section(insights: list[dict]) -> str:
    lines = []

    lines.append("=" * 50)
    lines.append("TODAY'S PRIORITIES")
    lines.append("=" * 50)

    if not insights:
        lines.append("\nNo critical insights detected. Store looks healthy.")
        return "\n".join(lines)

    top_priorities = _derive_top_priorities(insights)
    lines.append("\nToday's Priorities (Fix these first)")
    for idx, item in enumerate(top_priorities, start=1):
        title = _clean_text(item.get("title"), "Untitled issue")
        value = float(item.get("potential_value", 0) or 0)
        action_cta = _clean_text(item.get("action_cta"), "Review and resolve")
        label = "at risk" if item.get("impact_type") == "risk" else "potential"
        sign = "" if item.get("impact_type") == "risk" else "+"
        lines.append(f"{idx}. {title} ({sign}{format_currency(value)} {label})")
        lines.append(f"   {action_cta}")

    diagnosis_parts = [p.get("title", "").lower() for p in top_priorities]
    diagnosis = " + ".join(diagnosis_parts) if diagnosis_parts else "No urgent blockers detected"
    lines.append(f"\nStore Status: {'Weak' if any(i.get('severity') == 'high' for i in insights) else 'Stable'}")
    lines.append("Main issue: no recent sales and high dependency on a small customer base.")
    lines.append(f"Store Diagnosis: {diagnosis}.")

    churned_recovery = sum(
        float(i.get("potential_value", 0) or 0)
        for i in insights
        if i.get("title") == "Churned Customers"
    )
    returns_recovery = sum(
        float(i.get("potential_value", 0) or 0)
        for i in insights
        if i.get("title") == "High Return Rate Product"
    )
    recoverable_total = churned_recovery + returns_recovery
    risk_total = sum(float(i.get("potential_value", 0) or 0) for i in insights if i.get("impact_type") == "risk")
    lines.append("\nImpact Breakdown")
    lines.append(f"- Recoverable Revenue: +{format_currency(recoverable_total)}")
    if churned_recovery > 0:
        lines.append(f"  - Churned customers: {format_currency(churned_recovery)}")
    if returns_recovery > 0:
        lines.append(f"  - Returns reduction: {format_currency(returns_recovery)}")
    lines.append(f"- Risk Exposure: {format_currency(risk_total)} at risk")
    lines.append("\nWhat to do today (30 min plan)")
    for idx, step in enumerate(_build_30_min_plan(top_priorities), start=1):
        lines.append(f"{idx}. {step}")

    lines.append("\nKey Problems")
    for insight in _derive_key_issues(insights):
        icon = SEVERITY_ICON.get(insight["severity"], "[MEDIUM]")
        lines.append(f"\n{icon} {_with_money_language(insight['problem'], insight.get('potential_value', 0))}")
        lines.append(f"{_with_money_language(insight['impact'], insight.get('potential_value', 0))}")
        lines.append(f"Action: {insight['action']}")
        if insight.get("is_generatable"):
            lines.append(f"[Generate] {insight.get('action_cta', 'Run action')}")
        if insight.get("execution_note"):
            for line in [n for n in str(insight["execution_note"]).splitlines() if n.strip()][:3]:
                lines.append(line)

    return "\n".join(lines)


def format_inventory_section(data: dict) -> str:
    lines = []

    lines.append("=" * 50)
    lines.append("INVENTORY ISSUES")
    lines.append("=" * 50)

    out_of_stock = data.get("out_of_stock", [])
    critical = data.get("critical_stock", [])
    low = data.get("low_stock", [])

    grouped_oos = _group_inventory(out_of_stock)
    lines.append(f"\n- {len(out_of_stock)} out-of-stock -> losing sales")
    lines.append(f"- {len(critical)} critical stock")
    lines.append(f"- {len(low)} low stock")
    if grouped_oos:
        lines.append("\nTop priority:")
        for item in grouped_oos[:2]:
            lines.append(f"- {item['product_title']} ({item['variant_label']})")
    lines.append("Restock within 48h to protect revenue")

    return "\n".join(lines)


def format_customers_section(data: dict) -> str:
    lines = []

    lines.append("=" * 50)
    lines.append("CUSTOMER HEALTH")
    lines.append("=" * 50)

    churned = [c for c in data.get("churned", []) if _is_meaningful_customer(c)]
    never_returned = [c for c in data.get("never_returned", []) if _is_meaningful_customer(c)]
    loyal = [c for c in data.get("loyal", []) if _is_meaningful_customer(c)]
    health = data.get("health", {})
    loyal_revenue = sum(float(c.get("total_spent", 0) or 0) for c in loyal)
    top2_revenue = sum(float(c.get("total_spent", 0) or 0) for c in loyal[:2])
    concentration_pct = (top2_revenue / loyal_revenue * 100) if loyal_revenue > 0 else 0

    lines.append("\nCustomer Health")
    lines.append(
        f"- {concentration_pct:.0f}% of loyal revenue from top 2 customers ({'high risk' if concentration_pct >= 50 else 'balanced'})"
    )
    repeat_30 = int(health.get("repeat_customers_last_30d") or 0)
    lines.append(f"- {repeat_30} repeat purchases in last 30 days")
    lines.append(f"- {len(churned)} churned customers (>90 days)")
    lines.append(f"- {len(never_returned)} one-time buyers have not returned")
    lines.append("Focus: retention and new customer acquisition")

    unidentified = int(health.get("unidentified_customers") or 0)
    if unidentified > 0:
        lines.append(f"- {unidentified} unidentified customers (missing customer data)")

    return "\n".join(lines)


def format_revenue_section(data: dict) -> str:
    lines = []

    lines.append("=" * 50)
    lines.append("REVENUE INSIGHT")
    lines.append("=" * 50)

    summary = data.get("summary", {})
    total_orders = int(summary.get("total_orders", 0) or 0)
    net_revenue = float(summary.get("net_revenue", 0) or 0)
    trend = data.get("trend", {})
    current_7d = int(trend.get("current_7d_orders") or 0)
    previous_7d = int(trend.get("previous_7d_orders") or 0)
    delta_orders = current_7d - previous_7d
    lines.append(f"\nRevenue so far: {format_currency(net_revenue)}")
    lines.append(f"Last 7 days: {current_7d} orders (previous 7 days: {previous_7d})")
    lines.append("Sales are currently stalled." if current_7d == 0 else "Sales are active but volume is low.")
    lines.append("Main issue: low traffic and conversion, not pricing." if current_7d < 10 else "Main issue: improve conversion efficiency.")
    if current_7d == 0 and total_orders > 0:
        lines.append("Previous activity exists, but momentum has dropped.")
    elif delta_orders < 0:
        lines.append("Order trend is declining week over week.")
    lines.append("Action: prioritize traffic recovery and conversion fixes today.")

    return "\n".join(lines)


def format_final_summary_section(insights: list[dict], revenue: dict) -> str:
    lines = []
    lines.append("=" * 50)
    lines.append("FINAL SUMMARY")
    lines.append("=" * 50)
    current_7d = int((revenue.get("trend") or {}).get("current_7d_orders") or 0)
    if current_7d == 0:
        lines.append("\nRevenue is currently limited by product returns and customer churn.")
        lines.append("Fix these first to restore baseline performance.")
    else:
        lines.append("\nRevenue is currently constrained by concentration risk and conversion drag.")
        lines.append("Resolve these first to stabilize weekly performance.")
    return "\n".join(lines)


def _format_today_priorities(priorities: list[dict]) -> str:
    lines = ["=" * 50, "TODAY'S PRIORITIES", "=" * 50]
    if not priorities:
        lines.append("\nNo critical priorities today.")
        return "\n".join(lines)
    for idx, item in enumerate(priorities, start=1):
        value = float(item.get("potential_value", 0) or 0)
        label = "at risk" if item.get("impact_type") == "risk" else "potential"
        sign = "" if item.get("impact_type") == "risk" else "+"
        sev = str(item.get("severity", "medium")).upper()
        lines.append(
            f"\n{idx}. {sev} - {item.get('title', 'Untitled')} ({sign}{format_currency(value)} {label})"
        )
    return "\n".join(lines)


def _format_store_diagnosis(priorities: list[dict]) -> str:
    lines = ["=" * 50, "STORE DIAGNOSIS", "=" * 50]
    if not priorities:
        lines.append("\nStore is stable with no urgent blockers.")
        return "\n".join(lines)
    parts = [str(p.get("title") or "").lower() for p in priorities[:2]]
    lines.append(f"\nStatus: Weak")
    lines.append(f"Main issue: {' + '.join(parts)}")
    return "\n".join(lines)


def _format_money_snapshot(insights: list[dict]) -> str:
    lines = ["=" * 50, "MONEY SNAPSHOT", "=" * 50]
    churned_recovery = sum(float(i.get("potential_value", 0) or 0) for i in insights if i.get("title") == "Churned Customers")
    returns_recovery = sum(float(i.get("potential_value", 0) or 0) for i in insights if i.get("title") == "High Return Rate Product")
    risk_total = sum(float(i.get("potential_value", 0) or 0) for i in insights if i.get("impact_type") == "risk")
    recoverable = churned_recovery + returns_recovery
    net_impact = recoverable - risk_total
    net_sign = "+" if net_impact >= 0 else "-"
    lines.extend(
        [
            "",
            "| Metric | Value |",
            "|------|------:|",
            f"| Recoverable Revenue | +{format_currency(recoverable)} |",
            f"| Risk Exposure | {format_currency(risk_total)} |",
            f"| Net Impact | {net_sign}{format_currency(abs(net_impact))} |",
        ]
    )
    return "\n".join(lines)


def _format_execution_plan(priorities: list[dict]) -> str:
    lines = ["=" * 50, "TODAY'S EXECUTION PLAN", "=" * 50]
    for idx, step in enumerate(_build_30_min_plan(priorities)[:4], start=1):
        lines.append(f"\n{idx}. {step}")
    return "\n".join(lines)


def _format_key_problems(insights: list[dict], used_titles: set[str]) -> str:
    lines = ["=" * 50, "KEY PROBLEMS", "=" * 50]
    has_return = any(str(i.get("title") or "").lower() == "high return rate product" for i in insights)
    churned = next((i for i in insights if str(i.get("title") or "").lower() == "churned customers"), None)
    concentration = next((i for i in insights if "concentration" in str(i.get("title") or "").lower()), None)

    lines.append("")
    if has_return:
        lines.append("- High return rate product -> revenue leakage")
    if churned:
        lines.append(f"- Churned customers -> {format_currency(churned.get('potential_value', 0))} recoverable")
    if concentration:
        lines.append("- Revenue concentration -> dependency risk")

    if len(lines) == 4:
        key_issues = _remaining_key_issues(insights, used_titles)
        for issue in key_issues[:3]:
            lines.append(f"- {issue.get('title')} -> {_clean_text(issue.get('impact'), 'impact detected')}")
    return "\n".join(lines)


def _format_inventory_risk(inventory: dict) -> str:
    lines = ["=" * 50, "INVENTORY RISK", "=" * 50]
    out_of_stock = inventory.get("out_of_stock", [])
    critical = inventory.get("critical_stock", [])
    low = inventory.get("low_stock", [])
    lines.append(f"\n- {len(out_of_stock)} out-of-stock variants -> lost sales occurring")
    lines.append(f"- {len(critical)} critical stock items")
    lines.append(f"- {len(low)} low stock items")
    grouped = _group_inventory(out_of_stock)
    if grouped:
        lines.append("")
        lines.append("Top priority restocks:")
        for item in grouped[:3]:
            lines.append(f"- {item['product_title']}")
    return "\n".join(lines)


def _format_customer_risk(customers: dict) -> str:
    lines = ["=" * 50, "CUSTOMER RISK", "=" * 50]
    churned = [c for c in customers.get("churned", []) if _is_meaningful_customer(c)]
    never_returned = [c for c in customers.get("never_returned", []) if _is_meaningful_customer(c)]
    loyal = [c for c in customers.get("loyal", []) if _is_meaningful_customer(c)]
    health = customers.get("health", {})
    loyal_revenue = sum(float(c.get("total_spent", 0) or 0) for c in loyal)
    top2_revenue = sum(float(c.get("total_spent", 0) or 0) for c in loyal[:2])
    concentration_pct = (top2_revenue / loyal_revenue * 100) if loyal_revenue > 0 else 0
    lines.append(f"\n- Revenue concentration: top 2 customers = {concentration_pct:.0f}%")
    lines.append(f"- {len(churned)} churned customers (>90 days)")
    lines.append(f"- {int(health.get('repeat_customers_last_30d') or 0)} repeat purchases in last 30 days")
    lines.append("")
    lines.append("Insight:")
    lines.append("Losing one key customer would significantly impact revenue stability.")
    return "\n".join(lines)


def _format_revenue_status(revenue: dict) -> str:
    lines = ["=" * 50, "REVENUE SUMMARY", "=" * 50]
    summary = revenue.get("summary", {})
    trend = revenue.get("trend", {})
    current_7d = int(trend.get("current_7d_orders") or 0)
    previous_7d = int(trend.get("previous_7d_orders") or 0)
    net_revenue = float(summary.get("net_revenue", 0) or 0)
    status = "Stalled" if current_7d == 0 else "Active but weak"
    lines.extend(
        [
            "",
            "| Metric | Value |",
            "|--------|------:|",
            f"| Revenue | {format_currency(net_revenue)} |",
            f"| Orders (7d) | {current_7d} |",
            f"| Status | {status} |",
            "",
            "Insight:",
        ]
    )
    lines.append("Main issue is low traffic and conversion, not pricing.")
    if current_7d < previous_7d:
        lines.append("Order momentum is declining week over week.")
    return "\n".join(lines)


def format_full_report(summary: dict) -> str:
    logger.info("Formatting full report...")
    insights = summary.get("insights", [])
    priorities = _derive_top_priorities(insights)
    used_titles = _used_titles(priorities)
    inventory = summary.get("inventory", {})
    customers = summary.get("customers", {})
    revenue = summary.get("revenue", {})

    sections = [
        _format_today_priorities(priorities),
        _format_store_diagnosis(priorities),
        _format_money_snapshot(insights),
        _format_execution_plan(priorities),
        _format_key_problems(insights, used_titles),
        _format_inventory_risk(inventory),
        _format_customer_risk(customers),
        _format_revenue_status(revenue),
        format_final_summary_section(insights, revenue),
    ]

    report = "\n\n".join(sections)
    logger.info("Report formatted successfully.")
    return report