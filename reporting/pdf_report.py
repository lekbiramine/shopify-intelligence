from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from config.logging_config import get_logger
from reporting.formatter import format_currency, format_percent

logger = get_logger(__name__)


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "TitleCustom",
            parent=base["Title"],
            fontSize=20,
            leading=24,
            textColor=colors.HexColor("#0f172a"),
            spaceAfter=6,
        ),
        "meta": ParagraphStyle(
            "Meta",
            parent=base["Normal"],
            fontSize=9,
            textColor=colors.HexColor("#64748b"),
            spaceAfter=14,
        ),
        "section": ParagraphStyle(
            "SectionHeader",
            parent=base["Heading2"],
            fontSize=13,
            leading=16,
            textColor=colors.HexColor("#1e293b"),
            spaceBefore=10,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["Normal"],
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#0f172a"),
        ),
        "small": ParagraphStyle(
            "Small",
            parent=base["Normal"],
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#334155"),
        ),
    }


def _safe(value: object) -> str:
    if value is None:
        return "N/A"
    return " ".join(str(value).split())


def _format_anomaly_row(title: str, row: dict) -> str:
    if title == "Duplicate Orders":
        return (
            f"Customer {_safe(row.get('customer_id'))} | "
            f"Date: {_safe(row.get('order_date'))} | "
            f"Amount: {format_currency(row.get('total_price', 0))} | "
            f"Count: {_safe(row.get('order_count'))}"
        )
    if title == "Zero Value Orders":
        return (
            f"Order {_safe(row.get('order_id'))} | "
            f"{_safe(row.get('email'))} | "
            f"Amount: {format_currency(row.get('total_price', 0))}"
        )
    if title == "Abnormal Discounts":
        return (
            f"Order {_safe(row.get('order_id'))} | "
            f"{_safe(row.get('email'))} | "
            f"Discount: {_safe(row.get('discount_pct'))}%"
        )
    if title == "Active Products With No Sales":
        return f"{_safe(row.get('product_title'))} | Vendor: {_safe(row.get('vendor'))}"
    return " | ".join(
        f"{k}: {_safe(v)}"
        for k, v in row.items()
        if k
        in {
            "order_id",
            "customer_id",
            "email",
            "product_title",
            "vendor",
            "discount_pct",
            "order_count",
            "total_price",
            "order_date",
        }
    )


def _badge(severity: str) -> str:
    sev = (severity or "info").lower()
    if sev == "high":
        return '<font color="#b91c1c"><b>HIGH</b></font>'
    if sev == "medium":
        return '<font color="#b45309"><b>MEDIUM</b></font>'
    if sev == "low":
        return '<font color="#1d4ed8"><b>LOW</b></font>'
    return '<font color="#334155"><b>INFO</b></font>'


def _summary_table(summary: dict, style: dict[str, ParagraphStyle]) -> Table:
    rows = [
        ["Metric", "Value"],
        ["Total Orders", f"{summary.get('total_orders', 0)}"],
        ["Unique Customers", f"{summary.get('unique_customers', 0)}"],
        ["Gross Revenue", format_currency(summary.get("gross_revenue", 0))],
        ["Total Discounts", format_currency(summary.get("total_discounts", 0))],
        ["Net Revenue", format_currency(summary.get("net_revenue", 0))],
        ["Avg Order Value", format_currency(summary.get("avg_order_value", 0))],
    ]
    table = Table(rows, colWidths=[220, 280])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f8fafc")),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -1), 9),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


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
    story.append(Paragraph("Action Required", style["section"]))
    if insights:
        for insight in insights:
            story.append(
                Paragraph(
                    f"{_badge(_safe(insight.get('severity')))} - <b>{_safe(insight.get('title'))}</b>",
                    style["body"],
                )
            )
            story.append(Paragraph(f"Problem: {_safe(insight.get('problem'))}", style["small"]))
            story.append(Paragraph(f"Impact: {_safe(insight.get('impact'))}", style["small"]))
            story.append(Paragraph(f"Action: {_safe(insight.get('action'))}", style["small"]))
            story.append(Spacer(1, 6))
    else:
        story.append(Paragraph("No critical insights detected.", style["body"]))

    inventory = summary.get("inventory", {})
    story.append(Paragraph("Inventory Alerts", style["section"]))
    for title, items in (
        ("Out of Stock", inventory.get("out_of_stock", [])),
        ("Critical Stock", inventory.get("critical_stock", [])),
        ("Low Stock", inventory.get("low_stock", [])),
    ):
        story.append(Paragraph(f"<b>{title}</b> ({len(items)})", style["body"]))
        if items:
            for item in items[:25]:
                story.append(
                    Paragraph(
                        f"- {_safe(item.get('product_title'))} | {_safe(item.get('variant_title'))} | "
                        f"SKU: {_safe(item.get('sku'))} | Available: {_safe(item.get('total_available'))}",
                        style["small"],
                    )
                )
            if len(items) > 25:
                story.append(Paragraph(f"... and {len(items) - 25} more", style["small"]))
        else:
            story.append(Paragraph("None", style["small"]))
        story.append(Spacer(1, 4))

    customers = summary.get("customers", {})
    story.append(Paragraph("Customer Insights", style["section"]))
    for title, items in (
        ("Churned Customers", customers.get("churned", [])),
        ("One-time Customers", customers.get("never_returned", [])),
        ("Loyal Customers", customers.get("loyal", [])),
    ):
        story.append(Paragraph(f"<b>{title}</b> ({len(items)})", style["body"]))
        if items:
            for c in items[:20]:
                story.append(
                    Paragraph(
                        f"- {_safe(c.get('first_name'))} {_safe(c.get('last_name'))} | "
                        f"{_safe(c.get('email'))} | Spent: {format_currency(c.get('total_spent', 0))}",
                        style["small"],
                    )
                )
            if len(items) > 20:
                story.append(Paragraph(f"... and {len(items) - 20} more", style["small"]))
        else:
            story.append(Paragraph("None", style["small"]))
        story.append(Spacer(1, 4))

    revenue = summary.get("revenue", {})
    story.append(Paragraph("Revenue Summary", style["section"]))
    story.append(_summary_table(revenue.get("summary", {}), style))
    story.append(Spacer(1, 8))
    high_return = revenue.get("high_return_rate", [])
    story.append(Paragraph(f"<b>High Return Rate Products</b> ({len(high_return)})", style["body"]))
    if high_return:
        for p in high_return[:20]:
            story.append(
                Paragraph(
                    f"- {_safe(p.get('product_title'))} | Sold: {_safe(p.get('total_sold'))} | "
                    f"Returned: {_safe(p.get('total_returned'))} | Rate: {format_percent(p.get('return_rate', 0))}",
                    style["small"],
                )
            )
    else:
        story.append(Paragraph("None", style["small"]))

    anomalies = summary.get("anomalies", {})
    story.append(Paragraph("Anomalies", style["section"]))
    anomaly_groups = (
        ("Duplicate Orders", anomalies.get("duplicate_orders", [])),
        ("Zero Value Orders", anomalies.get("zero_value_orders", [])),
        ("Abnormal Discounts", anomalies.get("abnormal_discounts", [])),
        ("Active Products With No Sales", anomalies.get("no_sales_products", [])),
    )
    for title, items in anomaly_groups:
        story.append(Paragraph(f"<b>{title}</b> ({len(items)})", style["body"]))
        if items:
            for row in items[:20]:
                line = _format_anomaly_row(title, row)
                story.append(Paragraph(f"- {line}", style["small"]))
            if len(items) > 20:
                story.append(Paragraph(f"... and {len(items) - 20} more", style["small"]))
        else:
            story.append(Paragraph("None", style["small"]))
        story.append(Spacer(1, 4))

    doc.build(story)
    logger.info(f"PDF report written to {output_path}")
    return str(output_path)
