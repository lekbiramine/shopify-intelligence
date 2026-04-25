from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from config.logging_config import get_logger

logger = get_logger(__name__)


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "TitleCustom",
            parent=base["Title"],
            fontSize=20,
            leading=24,
            textColor=colors.HexColor("#0B1220"),
            spaceAfter=6,
        ),
        "meta": ParagraphStyle(
            "Meta",
            parent=base["Normal"],
            fontSize=9,
            textColor=colors.HexColor("#667085"),
            spaceAfter=14,
        ),
        "section_text": ParagraphStyle(
            "SectionText",
            parent=base["Normal"],
            fontSize=10,
            leading=12,
            textColor=colors.white,
            alignment=0,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["Normal"],
            fontSize=9.5,
            leading=14,
            textColor=colors.HexColor("#111827"),
        ),
        "muted": ParagraphStyle(
            "Muted",
            parent=base["Normal"],
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#475467"),
        ),
        "badge_high": ParagraphStyle(
            "BadgeHigh",
            parent=base["Normal"],
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#ffffff"),
        ),
        "badge_medium": ParagraphStyle(
            "BadgeMedium",
            parent=base["Normal"],
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#ffffff"),
        ),
    }


def _safe(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _format_currency(value: float) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


def _priority_rank(insight: dict) -> int:
    title = (insight.get("title") or "").lower()
    impact_type = (insight.get("impact_type") or "").lower()
    if impact_type == "risk" or "return" in title or "duplicate" in title or "discount" in title:
        return 0
    if "churn" in title or "dead inventory" in title:
        return 1
    return 2


def _top_priorities(insights: list[dict]) -> list[dict]:
    return sorted(
        insights,
        key=lambda i: (
            {"high": 0, "medium": 1, "low": 2}.get((i.get("severity") or "").lower(), 9),
            _priority_rank(i),
            -float(i.get("potential_value", 0) or 0),
        ),
    )[:3]


def _execution_plan(priorities: list[dict]) -> list[str]:
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
    return plan[:3] or ["Execute highest-value action first (10 min)"]


def _group_by_product(items: list[dict]) -> list[str]:
    grouped: dict[str, set[str]] = {}
    for item in items:
        product = _safe(item.get("product_title"))
        variant = _safe(item.get("variant_title"))
        grouped.setdefault(product, set()).add(variant)
    ranked = sorted(grouped.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    return [name for name, _ in ranked]


def _count_label(count: int, singular: str, plural: str) -> str:
    return singular if count == 1 else plural


def _section_header(text: str, style: dict[str, ParagraphStyle], bg_color: str = "#0f172a") -> Table:
    table = Table([[Paragraph(f"<b>{_safe(text)}</b>", style["section_text"])]], colWidths=[515])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(bg_color)),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _soft_table(rows: list[list[str]], col_widths: list[int]) -> Table:
    table = Table(rows, colWidths=col_widths)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAECF0")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#101828")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D0D5DD")),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F9FAFB")),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _callout_card(
    title: str,
    body_lines: list[str],
    title_style: ParagraphStyle,
    body_style: ParagraphStyle,
    border_color: str = "#D0D5DD",
    bg_color: str = "#F9FAFB",
) -> Table:
    rows = [[Paragraph(f"<b>{_safe(title)}</b>", title_style)]]
    for line in body_lines:
        if line and line.strip():
            rows.append([Paragraph(_safe(line), body_style)])
    card = Table(rows, colWidths=[515])
    card.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(bg_color)),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor(border_color)),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return card


def _severity_badge(severity: str) -> tuple[str, str]:
    sev = (severity or "medium").lower()
    if sev == "high":
        return ("HIGH", "#B42318")
    if sev == "medium":
        return ("MEDIUM", "#B54708")
    return ("LOW", "#175CD3")


def create_report_pdf(summary: dict, output_dir: str = "reports") -> str:
    style = _styles()
    generated_at = datetime.now(timezone.utc)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"store-intelligence-{generated_at.strftime('%Y%m%d')}.pdf"
    output_path = out_dir / filename

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=LETTER,
        leftMargin=40,
        rightMargin=40,
        topMargin=40,
        bottomMargin=40,
        title="Store Intelligence Report",
        author="Shopify Automation Pipeline",
    )

    story = [
        Paragraph("Store Intelligence Report", style["title"]),
        Paragraph(f"Generated {generated_at.strftime('%Y-%m-%d %H:%M UTC')}", style["meta"]),
    ]
    insights = summary.get("insights", [])
    priorities = _top_priorities(insights)
    used_titles = {str(p.get("title") or "") for p in priorities}

    story.append(_section_header("TODAY'S PRIORITIES", style, "#101828"))
    story.append(Spacer(1, 6))
    for idx, p in enumerate(priorities, start=1):
        sev, sev_color = _severity_badge(str(p.get("severity") or "medium"))
        impact = float(p.get("potential_value", 0) or 0)
        impact_label = "at risk" if p.get("impact_type") == "risk" else "potential"
        sign = "" if p.get("impact_type") == "risk" else "+"
        badge = Table([[Paragraph(f"<b>{sev}</b>", style["badge_high"])]], colWidths=[50])
        badge.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(sev_color)),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        line = Table(
            [[badge, Paragraph(f"{idx}. {_safe(p.get('title'))} ({sign}{_format_currency(impact)} {impact_label})", style["body"])]],
            colWidths=[58, 450],
        )
        line.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story.append(line)
        story.append(Spacer(1, 4))

    story.append(Spacer(1, 4))
    story.append(_section_header("STORE DIAGNOSIS", style, "#1D2939"))
    status = "Weak" if any(i.get("severity") == "high" for i in insights) else "Stable"
    main_issue = " + ".join((str(i.get("title") or "").lower() for i in priorities[:2])) or "no urgent blockers"
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"<b>Status:</b> {status}", style["body"]))
    story.append(Paragraph(f"<b>Main issue:</b> {main_issue}", style["body"]))

    churned_recovery = sum(float(i.get("potential_value", 0) or 0) for i in insights if i.get("title") == "Churned Customers")
    returns_recovery = sum(float(i.get("potential_value", 0) or 0) for i in insights if i.get("title") == "High Return Rate Product")
    recoverable = churned_recovery + returns_recovery
    risk = sum(float(i.get("potential_value", 0) or 0) for i in insights if i.get("impact_type") == "risk")
    net_impact = recoverable - risk
    net_sign = "+" if net_impact >= 0 else "-"

    story.append(Spacer(1, 10))
    story.append(_section_header("MONEY SNAPSHOT", style, "#054F31"))
    story.append(Spacer(1, 6))
    story.append(
        _soft_table(
            [
                ["Type", "Value"],
                ["Recoverable Revenue", f"+{_format_currency(recoverable)}"],
                ["Risk Exposure", _format_currency(risk)],
                ["Net Impact", f"{net_sign}{_format_currency(abs(net_impact))}"],
            ],
            [300, 215],
        )
    )

    story.append(Spacer(1, 10))
    story.append(_section_header("TODAY'S EXECUTION PLAN", style, "#0B4A6F"))
    plan_lines = [f"{idx}. {_safe(step)}" for idx, step in enumerate(_execution_plan(priorities), start=1)]
    story.append(
        _callout_card(
            "Execute in order",
            plan_lines,
            style["body"],
            style["muted"],
            border_color="#BFC6D4",
            bg_color="#F8FAFC",
        )
    )

    story.append(Spacer(1, 10))
    story.append(_section_header("KEY ISSUES", style, "#7A271A"))
    has_return = any(str(i.get("title") or "").lower() == "high return rate product" for i in insights)
    churned_item = next((i for i in insights if str(i.get("title") or "").lower() == "churned customers"), None)
    concentration_item = next((i for i in insights if "concentration" in str(i.get("title") or "").lower()), None)
    key_issue_lines: list[str] = []
    if has_return:
        key_issue_lines.append("- High return rate product -> revenue leakage")
    if churned_item:
        key_issue_lines.append(f"- Churned customers -> {_format_currency(churned_item.get('potential_value', 0))} recoverable")
    if concentration_item:
        key_issue_lines.append("- Revenue concentration -> dependency risk")
    if not key_issue_lines:
        key_issue_lines.append("- No additional high-impact issue summary available")
    story.append(
        _callout_card(
            "Core issue summary",
            key_issue_lines[:3],
            style["body"],
            style["muted"],
            border_color="#BFC6D4",
            bg_color="#F8FAFC",
        )
    )

    inventory = summary.get("inventory", {})
    out_of_stock = inventory.get("out_of_stock", [])
    critical = inventory.get("critical_stock", [])
    low = inventory.get("low_stock", [])
    top_stock = _group_by_product(out_of_stock)[:3]
    story.append(Spacer(1, 10))
    story.append(_section_header("INVENTORY RISK", style, "#1D4E89"))
    inventory_lines = [
        f"- {len(out_of_stock)} out-of-stock variants -> lost sales occurring",
        f"- {len(critical)} critical stock {_count_label(len(critical), 'item', 'items')}",
        f"- {len(low)} low stock {_count_label(len(low), 'item', 'items')}",
    ]
    if top_stock:
        inventory_lines.append("")
        inventory_lines.append("Top priority restocks:")
        for row in top_stock:
            inventory_lines.append(f"- {_safe(row)}")
    story.append(
        _callout_card(
            "Stock pressure summary",
            inventory_lines,
            style["body"],
            style["muted"],
            border_color="#BFC6D4",
            bg_color="#F8FAFC",
        )
    )

    customers = summary.get("customers", {})
    loyal = customers.get("loyal", [])
    churned = customers.get("churned", [])
    health = customers.get("health", {})
    loyal_revenue = sum(float(c.get("total_spent", 0) or 0) for c in loyal)
    top2 = sum(float(c.get("total_spent", 0) or 0) for c in loyal[:2])
    concentration = (top2 / loyal_revenue * 100) if loyal_revenue else 0
    story.append(Spacer(1, 10))
    story.append(_section_header("CUSTOMER RISK", style, "#5925DC"))
    story.append(
        _callout_card(
            "Customer concentration snapshot",
            [
                f"- Revenue concentration: 2 customers = {concentration:.0f}%",
                f"- {len(churned)} churned customers (>90 days)",
                f"- {int(health.get('repeat_customers_last_30d') or 0)} repeat purchases in last 30 days",
                "",
                "Insight: Losing one key customer could materially reduce revenue stability.",
            ],
            style["body"],
            style["muted"],
            border_color="#BFC6D4",
            bg_color="#F8FAFC",
        )
    )

    revenue = summary.get("revenue", {})
    rev_summary = revenue.get("summary", {})
    trend = revenue.get("trend", {})
    current_7d = int(trend.get("current_7d_orders") or 0)
    net_revenue = float(rev_summary.get("net_revenue", 0) or 0)
    status = "Stalled" if current_7d == 0 else "Active but weak"
    story.append(Spacer(1, 10))
    story.append(_section_header("REVENUE SUMMARY", style, "#344054"))
    story.append(
        _soft_table(
            [
                ["Metric", "Value"],
                ["Revenue", _format_currency(net_revenue)],
                ["Orders (7d)", str(current_7d)],
                ["Status", status],
            ],
            [300, 215],
        )
    )
    story.append(Spacer(1, 6))
    story.append(Paragraph("<b>Insight:</b> Main issue is low traffic and conversion, not pricing.", style["muted"]))

    story.append(Spacer(1, 10))
    story.append(_section_header("FINAL SUMMARY", style, "#101828"))
    if current_7d == 0:
        summary_lines = [
            "Revenue is currently limited by product returns and customer churn.",
            "Fix these first to restore baseline performance.",
        ]
    else:
        summary_lines = [
            "Revenue is currently constrained by concentration risk and conversion drag.",
            "Resolve these first to stabilize weekly performance.",
        ]
    story.append(
        _callout_card(
            "Executive Recommendation",
            summary_lines,
            style["body"],
            style["muted"],
            border_color="#BFC6D4",
            bg_color="#F8FAFC",
        )
    )

    doc.build(story)
    logger.info(f"PDF report written to {output_path}")
    return str(output_path)
