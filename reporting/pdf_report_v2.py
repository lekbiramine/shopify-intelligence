from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from config.logging_config import get_logger

logger = get_logger(__name__)

_STATUS_LABELS = {"pending": "pending", "in_progress": "in_progress", "completed": "completed", "ignored": "ignored"}
_STATUS_ORDER = {"pending": 0, "in_progress": 1, "completed": 2, "ignored": 3}
_TYPE_EFFORT = {"pause_sku": 1.20, "discount_audit": 1.15, "duplicate_audit": 1.10, "win_back": 1.05, "acquisition": 1.00, "dead_inventory": 0.95}
_TYPE_LABELS = {
    "pause_sku": "High Return Product",
    "discount_audit": "Discount Leakage",
    "duplicate_audit": "Duplicate Orders",
    "win_back": "Recover Churned Customers",
    "acquisition": "Fix Revenue Concentration Risk",
    "dead_inventory": "Reduce Dead Inventory Risk",
    "general": "Operational Opportunity",
}
_ENTITY_LABELS = {
    "revenue_concentration_risk": "Revenue Concentration Risk",
    "dead_inventory": "Dead Inventory",
    "churn_90d": "Churned Customers",
    "pause_sku": "High Return Product",
}


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("TitleCustom", parent=base["Title"], fontSize=20, leading=24, textColor=colors.HexColor("#0B1220"), spaceAfter=6),
        "meta": ParagraphStyle("Meta", parent=base["Normal"], fontSize=9, textColor=colors.HexColor("#667085"), spaceAfter=14),
        "section_text": ParagraphStyle("SectionText", parent=base["Normal"], fontSize=10, leading=12, textColor=colors.white, alignment=0),
        "body": ParagraphStyle("Body", parent=base["Normal"], fontSize=9.5, leading=14, textColor=colors.HexColor("#111827")),
        "muted": ParagraphStyle("Muted", parent=base["Normal"], fontSize=9, leading=12, textColor=colors.HexColor("#475467")),
    }


def _safe(value: object) -> str:
    return "" if value is None else " ".join(str(value).split())


def _to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _format_currency(value: float) -> str:
    return f"${_to_float(value):,.2f}"


def _title_case_from_key(value: str) -> str:
    clean = (value or "").replace("_", " ").replace("-", " ").strip()
    return " ".join(part.capitalize() for part in clean.split())


def _business_label(raw_value: object) -> str:
    value = _safe(raw_value)
    if not value:
        return ""
    lowered = value.lower()
    if lowered in _ENTITY_LABELS:
        return _ENTITY_LABELS[lowered]
    if "_" in value or "-" in value:
        return _title_case_from_key(value)
    return value


def _section_header(text: str, style: dict[str, ParagraphStyle], bg_color: str = "#0f172a") -> Table:
    table = Table([[Paragraph(f"<b>{_safe(text)}</b>", style["section_text"])]], colWidths=[515])
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(bg_color)), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return table


def _soft_table(rows: list[list[str]], col_widths: list[int]) -> Table:
    table = Table(rows, colWidths=col_widths)
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAECF0")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#101828")), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTNAME", (0, 1), (-1, -1), "Helvetica"), ("FONTSIZE", (0, 0), (-1, -1), 9), ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D0D5DD")), ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F9FAFB")), ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    return table


def _due_at_to_urgency(task: dict, now_utc: datetime) -> float:
    due_at = task.get("due_at")
    if due_at is None:
        p = str(task.get("priority") or "medium").lower()
        return 1.20 if p == "high" else 0.90 if p == "low" else 1.00
    try:
        delta_hours = (due_at - now_utc).total_seconds() / 3600
    except Exception:
        return 1.00
    if delta_hours <= 0:
        return 1.30
    if delta_hours <= 24:
        return 1.20
    if delta_hours <= 72:
        return 1.10
    return 1.00


def _effort_factor(task: dict) -> float:
    return _TYPE_EFFORT.get(str(task.get("type") or "general").lower(), 1.00)


def _task_entity(task: dict) -> str:
    entity = _business_label(task.get("primary_entity_id"))
    if entity:
        return entity
    source_title = _business_label((task.get("metadata_json") or {}).get("source_title"))
    return source_title or "store"


def _task_name(task: dict) -> str:
    title = _safe(task.get("title"))
    return title or _TYPE_LABELS.get(str(task.get("type") or "general").lower(), "Operational Opportunity")


def _priority_tier(score: float) -> str:
    if score >= 500:
        return "High priority"
    if score >= 150:
        return "Medium priority"
    return "Priority"


def _execution_plan_line(task: dict) -> str:
    task_name = _task_name(task)
    entity = _task_entity(task)
    score = _to_float(task.get("_priority_score"))
    impact = _format_currency(_to_float(task.get("expected_impact")))
    detail = f" ({entity})" if entity and entity.lower() not in task_name.lower() else ""
    return f"{task_name}{detail} - {_priority_tier(score)} ({impact} impact)."


def _normalize_tasks(task_sections: dict | None) -> list[dict]:
    tasks = list((task_sections or {}).get("tasks", []))
    tasks.sort(key=lambda t: (_STATUS_ORDER.get(str(t.get("status") or "pending").lower(), 9), -_to_float(t.get("expected_impact")), str(t.get("title") or "").lower(), int(t.get("id") or 0)))
    return tasks


def _rank_active_tasks(tasks: list[dict], now_utc: datetime) -> list[dict]:
    ranked = []
    for task in tasks:
        if str(task.get("status") or "pending").lower() not in {"pending", "in_progress"}:
            continue
        impact = max(_to_float(task.get("expected_impact")), 0.0)
        score = impact * _due_at_to_urgency(task, now_utc) * _effort_factor(task)
        ranked.append({**task, "_priority_score": round(score, 4)})
    ranked.sort(key=lambda t: (-_to_float(t.get("_priority_score")), -_to_float(t.get("expected_impact")), str(t.get("title") or "").lower(), int(t.get("id") or 0)))
    return ranked


def _business_snapshot(summary: dict) -> dict:
    trend = summary.get("revenue", {}).get("trend", {})
    customers = summary.get("customers", {})
    inventory = summary.get("inventory", {})
    current_7d = int(trend.get("current_7d_orders") or 0)
    previous_7d = int(trend.get("previous_7d_orders") or 0)
    delta = current_7d - previous_7d
    delta_pct = (delta / previous_7d * 100.0) if previous_7d > 0 else (100.0 if current_7d > 0 else 0.0)
    churn_risk = len(customers.get("churned", []))
    inventory_risk = len(inventory.get("out_of_stock", [])) + len(inventory.get("critical_stock", []))
    loyal = customers.get("loyal", [])
    loyal_revenue = sum(_to_float(c.get("total_spent")) for c in loyal)
    top2_revenue = sum(_to_float(c.get("total_spent")) for c in loyal[:2])
    concentration_risk = (top2_revenue / loyal_revenue * 100.0) if loyal_revenue > 0 else 0.0
    return {"current_7d_orders": current_7d, "previous_7d_orders": previous_7d, "delta_orders": delta, "delta_pct": delta_pct, "churn_risk_count": churn_risk, "inventory_risk_count": inventory_risk, "concentration_risk_pct": concentration_risk}


def create_report_pdf(summary: dict, output_dir: str = "reports", task_sections: dict | None = None, *, store_id: int) -> str:
    style = _styles()
    generated_at = datetime.now(timezone.utc)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / f"store-intelligence-store-{store_id}-{generated_at.strftime('%Y%m%d-%H%M%S')}.pdf"

    tasks = _normalize_tasks(task_sections)
    ranked_active_tasks = _rank_active_tasks(tasks, generated_at)
    snapshot = _business_snapshot(summary)
    top_task = ranked_active_tasks[0] if ranked_active_tasks else None

    executive_summary = (
        f"The store currently has {len(ranked_active_tasks)} active priorities. Revenue trend is "
        f"{snapshot['delta_orders']:+d} order(s) week over week ({snapshot['delta_pct']:+.1f}%). "
        f"Primary pressure comes from churn ({snapshot['churn_risk_count']}) and inventory risk ({snapshot['inventory_risk_count']}). "
        f"Highest impact opportunity: {_task_name(top_task) if top_task else 'maintain current execution cadence'}."
    )

    story = [Paragraph("Store Intelligence Report", style["title"]), Paragraph(f"Generated {generated_at.strftime('%Y-%m-%d %H:%M UTC')}", style["meta"])]

    story.append(_section_header("EXECUTIVE SUMMARY", style, "#101828"))
    story.append(Spacer(1, 6))
    story.append(Paragraph(executive_summary, style["body"]))

    story.append(Spacer(1, 12))
    story.append(_section_header("ACTIVE TASKS", style, "#0B4A6F"))
    story.append(Spacer(1, 6))
    if tasks:
        rows = [["Task", "Status", "Expected Impact", "Linked Entity"]]
        for task in tasks:
            rows.append(
                [
                    Paragraph(_task_name(task), style["body"]),
                    _STATUS_LABELS.get(str(task.get("status") or "pending").lower(), "pending"),
                    _format_currency(_to_float(task.get("expected_impact"))),
                    Paragraph(_task_entity(task), style["body"]),
                ]
            )
        story.append(_soft_table(rows, [250, 80, 95, 90]))
    else:
        story.append(Paragraph("No tasks are currently tracked for this store.", style["muted"]))

    story.append(Spacer(1, 12))
    story.append(_section_header("PRIORITY EXECUTION PLAN", style, "#054F31"))
    story.append(Spacer(1, 6))
    if ranked_active_tasks:
        for idx, task in enumerate(ranked_active_tasks[:5], start=1):
            story.append(Paragraph(f"{idx}. {_execution_plan_line(task)}", style["body"]))
    else:
        story.append(Paragraph("No pending or in-progress tasks to prioritize.", style["muted"]))

    story.append(Spacer(1, 12))
    story.append(_section_header("BUSINESS HEALTH SNAPSHOT", style, "#1D2939"))
    story.append(Spacer(1, 6))
    story.append(_soft_table([["Metric", "Value"], ["Revenue trend (7d vs prior 7d)", f"{snapshot['current_7d_orders']} vs {snapshot['previous_7d_orders']} ({snapshot['delta_orders']:+d}, {snapshot['delta_pct']:+.1f}%)"], ["Churn risk", f"{snapshot['churn_risk_count']} customers inactive >90 days"], ["Inventory risk", f"{snapshot['inventory_risk_count']} variants out-of-stock/critical"], ["Concentration risk", f"Top 2 loyal customers represent {snapshot['concentration_risk_pct']:.1f}% of loyal revenue"]], [235, 280]))

    story.append(Spacer(1, 12))
    story.append(_section_header("FINAL RECOMMENDATION", style, "#101828"))
    story.append(Spacer(1, 6))
    recommendation = (
        f"Execute {_task_name(top_task)} first, then continue in ranked order to maximize impact while reducing operational risk."
        if top_task
        else "Maintain monitoring cadence and generate new tasks only when measurable risk or upside appears."
    )
    story.append(Paragraph(recommendation, style["body"]))

    doc = SimpleDocTemplate(str(output_path), pagesize=LETTER, leftMargin=40, rightMargin=40, topMargin=40, bottomMargin=40, title="Store Intelligence Report", author="Shopify Automation Pipeline")
    doc.build(story)
    logger.info("PDF report written to %s", output_path)
    return str(output_path)
