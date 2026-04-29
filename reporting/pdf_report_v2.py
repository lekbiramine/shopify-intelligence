from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime, timezone
from pathlib import Path
import re

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
_PRIORITY_FORMULA = "Value + (Daily Loss x 7-day)"


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("TitleCustom", parent=base["Title"], fontSize=20, leading=24, textColor=colors.HexColor("#0B1220"), spaceAfter=6),
        "meta": ParagraphStyle("Meta", parent=base["Normal"], fontSize=9, textColor=colors.HexColor("#667085"), spaceAfter=14),
        "section_text": ParagraphStyle("SectionText", parent=base["Normal"], fontSize=10, leading=12, textColor=colors.white, alignment=0),
        "body": ParagraphStyle("Body", parent=base["Normal"], fontSize=10, leading=15, textColor=colors.HexColor("#111827")),
        "muted": ParagraphStyle("Muted", parent=base["Normal"], fontSize=9.2, leading=13, textColor=colors.HexColor("#475467")),
        "action_title": ParagraphStyle("ActionTitle", parent=base["Normal"], fontSize=10.5, leading=15, textColor=colors.HexColor("#101828"), spaceAfter=2),
        "action_meta": ParagraphStyle("ActionMeta", parent=base["Normal"], fontSize=9.2, leading=13, textColor=colors.HexColor("#344054"), spaceAfter=2),
        "action_note": ParagraphStyle("ActionNote", parent=base["Normal"], fontSize=9, leading=12, textColor=colors.HexColor("#667085"), spaceAfter=2),
        "action_label": ParagraphStyle("ActionLabel", parent=base["Normal"], fontSize=9.2, leading=12, textColor=colors.HexColor("#344054"), spaceAfter=1),
    }


def _safe(value: object) -> str:
    return "" if value is None else " ".join(str(value).split())


def _to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_float_optional(value: object) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int_optional(value: object) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _format_currency(value: float) -> str:
    v = _to_float(value)
    try:
        q = Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return f"${q:,.2f}"
    except (InvalidOperation, ValueError):
        return "$0.00"


def _format_money_per_day(value: float, days: int = 30) -> str:
    v = max(_to_float(value), 0.0)
    if v <= 0:
        return "$0.00/day"
    d = max(int(days), 1)
    return f"${(v / d):,.2f}/day"


def _format_percent(value: object) -> str:
    return f"{_to_float(value):.2f}%"


def _has_broken_placeholder(text: str) -> bool:
    t = _safe(text).lower()
    if not t:
        return True
    patterns = [
        r"\b[-+]\s*(day|days|week|weeks|order|orders)\b",
        r"\b(within|for)\s*[-+]\s*(day|days|week|weeks)\b",
        r"\brecover\s*[-+]\s*orders\b",
        r"\breturn rate\b$",
        r"\bof loyal revenue\b$",
    ]
    return any(re.search(p, t) for p in patterns)


def _extract_percent(text: object) -> float | None:
    t = _safe(text)
    if not t:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", t)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _extract_count(text: object) -> int | None:
    t = _safe(text)
    if not t:
        return None
    m = re.search(r"\b(\d+)\b", t)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _display_customer_name(customer: dict) -> str:
    first = _safe(customer.get("first_name"))
    last = _safe(customer.get("last_name"))
    name = " ".join([part for part in [first, last] if part]).strip()
    if name:
        return name
    email = _safe(customer.get("email"))
    if email:
        return email
    cid = customer.get("customer_id") or customer.get("id")
    return f"Customer {cid}" if cid is not None else ""


def _format_units(value: object) -> str:
    iv = _to_int_optional(value)
    if iv is None:
        return ""
    return f"{iv} unit" if iv == 1 else f"{iv} units"


def _safe_render_text(value: object, *, max_len: int = 180) -> str:
    text = _safe(value)
    if not text or _has_broken_placeholder(text):
        return ""
    if len(text) > max_len:
        text = text[: max_len - 3].rstrip() + "..."
    return text


def _strip_weak_language(value: object) -> str:
    text = _safe(value)
    if not text:
        return ""
    text = re.sub(r"\blikely\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bmay\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bexpected to\b", "Target:", text, flags=re.IGNORECASE)
    return " ".join(text.split()).strip(" ,.")


def _soft_bullets(lines: list[str], max_items: int = 8) -> str:
    cleaned = ["• " + _safe(x) for x in (lines or []) if _safe(x)]
    if not cleaned:
        return ""
    return "<br/>".join(cleaned[:max_items])


def _prioritize_insights(insights: list[dict]) -> list[dict]:
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    return sorted(
        list(insights or []),
        key=lambda i: (
            severity_rank.get(str(i.get("severity") or "low").lower(), 9),
            0 if str(i.get("impact_type") or "").lower() == "risk" else 1,
            -_to_float(i.get("potential_value")),
            str(i.get("title") or "").lower(),
        ),
    )


def _quick_wins(insights: list[dict], summary: dict) -> list[dict]:
    ranked = _prioritize_insights(insights)
    wins: list[dict] = []

    for i in ranked:
        title = str(i.get("title") or "").strip()
        if not title:
            continue
        wins.append(i)
        if len(wins) >= 3:
            break

    inventory = summary.get("inventory", {}) or {}
    oos = list(inventory.get("out_of_stock", []) or [])
    if oos:
        top = sorted(oos, key=lambda x: _to_float(x.get("price")), reverse=True)[:3]
        wins.append(
            {
                "title": "Inventory Risk",
                "severity": "high",
                "impact_type": "risk",
                "potential_value": 0.0,
                "problem": f"{len(oos)} variants are out of stock and blocking checkout conversions.",
                "action": "Restock the top variants first and re-enable any paused ads once stock is confirmed.",
                "how_calculated": "Out-of-stock variants = summed available inventory == 0 across locations.",
                "time_window": "Current inventory snapshot.",
                "exact_items": [f"{_safe(t.get('product_title'))} — {_safe(t.get('variant_title'))} — SKU {_safe(t.get('sku'))}" for t in top],
                "expected_outcome": "Prevent immediate lost sales and recover conversion within 24–72 hours.",
            }
        )

    return wins[:4]


def _confidence(insight: dict) -> str:
    return str(insight.get("confidence") or "high").lower()


def _money_label(insight: dict) -> str:
    value = _to_float(insight.get("potential_value"))
    impact_type = str(insight.get("impact_type") or "").lower()
    if impact_type == "risk":
        return f"{_format_currency(value)} at risk"
    return f"{_format_currency(value)} recoverable"


def _executive_action_title(item: dict) -> str:
    title = str(item.get("title") or "").lower()
    exact_items = [_safe(x) for x in (item.get("exact_items") or []) if _safe(x)]
    focus = _clean_entity_name(exact_items[0]) if exact_items else ""
    if "churn" in title:
        return "Recover churned customers via 48h 10% offer"
    if "return" in title:
        if focus:
            return f"Pause ads for high-return product ({focus[:42]})"
        return "Pause high-return product ads"
    if "concentration" in title or "high-value" in title:
        return "Reduce revenue concentration risk from top customers"
    if "dead inventory" in title or "inventory" in title:
        return "Clear dead inventory via discount and bundling"
    if focus:
        return f"Execute profitability action for {focus[:48]}"
    return "Execute store profitability action"


def _clean_entity_name(value: object) -> str:
    text = _safe(value)
    if not text:
        return ""
    text = re.sub(r"\b(product_id|variant_id|customer_id|id)\s*=\s*\d+\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bSKU\s*[:#-]?\s*[A-Za-z0-9_-]+\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\([^)]*\d+[^)]*\)", "", text)
    for sep in ["—", "-", "|"]:
        if sep in text:
            text = text.split(sep, 1)[0].strip()
    return " ".join(text.split())


def _action_kind(item: dict) -> str:
    title = str(item.get("title") or "").lower()
    if "churn" in title:
        return "churn"
    if "return" in title:
        return "return"
    if "concentration" in title or "high-value" in title:
        return "concentration"
    if "dead inventory" in title:
        return "dead_inventory"
    if "out of stock" in title or "inventory risk" in title:
        return "out_of_stock"
    if "inventory" in title:
        return "inventory"
    return "general"


def _churn_items(summary: dict) -> list[str]:
    churned = list(summary.get("customers", {}).get("churned", []) or [])
    ranked = sorted(churned, key=lambda c: _to_float(c.get("total_spent")), reverse=True)[:4]
    lines: list[str] = []
    for c in ranked:
        name = _display_customer_name(c)
        days = _to_int_optional(c.get("days_since_last_order"))
        orders = max(_to_int_optional(c.get("orders_count")) or 0, 1)
        total_spent = _to_float_optional(c.get("total_spent"))
        if not name or days is None or total_spent is None:
            continue
        aov = total_spent / orders
        lines.append(f"{name} — {days}d inactive — est. AOV {_format_currency(aov)}")
    return lines


def _return_items(summary: dict) -> list[str]:
    products = list(summary.get("revenue", {}).get("high_return_rate", []) or [])[:4]
    lines: list[str] = []
    for p in products:
        name = _clean_entity_name(p.get("product_title"))
        rate = _to_float_optional(p.get("return_rate"))
        returned = _to_int_optional(p.get("total_returned"))
        if not name or rate is None or returned is None:
            continue
        lines.append(f"{name} — {rate * 100:.1f}% return rate — {returned} returned unit{'s' if returned != 1 else ''}")
    return lines


def _concentration_items(summary: dict) -> list[str]:
    loyal = list(summary.get("customers", {}).get("loyal", []) or [])[:4]
    lines: list[str] = []
    for c in loyal:
        name = _display_customer_name(c)
        spent = _to_float_optional(c.get("total_spent"))
        orders = _to_int_optional(c.get("orders_count"))
        if not name or spent is None or orders is None:
            continue
        lines.append(f"{name} — spend {_format_currency(spent)} — {orders} orders")
    return lines


def _inventory_items(summary: dict) -> list[str]:
    inventory = list(summary.get("inventory", {}).get("out_of_stock", []) or [])[:4]
    lines: list[str] = []
    for row in inventory:
        name = _clean_entity_name(row.get("product_title"))
        qty = _to_int_optional(row.get("total_available"))
        price = _to_float_optional(row.get("price"))
        if not name or qty is None:
            continue
        price_part = f" — price {_format_currency(price)}" if price is not None else ""
        lines.append(f"{name} — inventory {qty} units{price_part}")
    return lines


def _dead_inventory_items(summary: dict) -> list[str]:
    low = list(summary.get("inventory", {}).get("low_stock", []) or [])
    critical = list(summary.get("inventory", {}).get("critical_stock", []) or [])
    pool = low + critical
    lines: list[str] = []
    seen: set[str] = set()
    for row in pool:
        name = _clean_entity_name(row.get("product_title"))
        sku = _safe(row.get("sku"))
        qty = _to_int_optional(row.get("total_available"))
        if not name or qty is None or qty <= 0:
            continue
        key = f"{name}|{sku}"
        if key in seen:
            continue
        seen.add(key)
        sku_txt = f" (SKU: {sku})" if sku else ""
        lines.append(f"{name}{sku_txt} — inventory: {qty} units — sales: 0 in last 90d")
        if len(lines) >= 4:
            break
    return lines


def _financial_summary(insights: list[dict]) -> dict[str, float]:
    recoverable = sum(
        _to_float(i.get("potential_value"))
        for i in insights
        if str(i.get("impact_type") or "").lower() != "risk" and _to_float(i.get("potential_value")) > 0
    )
    risk = sum(
        _to_float(i.get("potential_value"))
        for i in insights
        if str(i.get("impact_type") or "").lower() == "risk" and _to_float(i.get("potential_value")) > 0
    )
    return {
        "recoverable": recoverable,
        "risk": risk,
        "net": recoverable + risk,
    }


def _action_priority_metrics(item: dict) -> dict[str, float]:
    recoverable = max(_to_float(item.get("potential_value")), 0.0)
    loss_days = max(int(item.get("loss_window_days") or 7), 1)
    daily_loss = recoverable / loss_days if recoverable > 0 else 0.0
    priority_score = recoverable + (daily_loss * 7.0)
    return {"recoverable": recoverable, "daily_loss": daily_loss, "priority_score": priority_score}


def _action_uniqueness_key(item: dict) -> str:
    kind = _action_kind(item)
    if kind in {"inventory", "out_of_stock"}:
        return "out_of_stock"
    return kind


def _rank_priority_actions(insights: list[dict], max_actions: int = 5) -> list[dict]:
    ranked = [i for i in _prioritize_insights(insights) if _to_float(i.get("potential_value")) > 0]
    ranked.sort(
        key=lambda i: (
            -_action_priority_metrics(i)["priority_score"],
            -_action_priority_metrics(i)["recoverable"],
            str(i.get("title") or "").lower(),
        )
    )
    unique: list[dict] = []
    seen: set[str] = set()
    for item in ranked:
        key = _action_uniqueness_key(item)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
        if len(unique) >= max_actions:
            break
    return unique


def _delta_text_from_pct(pct: float | None) -> str:
    if pct is None:
        return "Δ unavailable"
    arrow = "↑" if pct > 0 else "↓" if pct < 0 else "→"
    return f"{arrow}{abs(pct):.1f}%"


def _trend_label(pct: float | None, *, higher_is_risk: bool) -> str:
    if pct is None:
        return "unknown trend"
    if abs(pct) < 0.01:
        return "stable"
    if higher_is_risk:
        return "increasing risk" if pct > 0 else "improving"
    return "improving" if pct > 0 else "increasing risk"


def _severity_label(metric: str, value: float | int | None) -> str:
    if value is None:
        return "MEDIUM"
    v = float(value)
    key = metric.lower()
    if key == "inventory_pressure":
        if v >= 20:
            return "HIGH"
        if v >= 8:
            return "MEDIUM"
        return "LOW"
    if key == "inactive_customers":
        if v >= 10:
            return "HIGH"
        if v >= 4:
            return "MEDIUM"
        return "LOW"
    if key == "revenue_concentration":
        if v >= 70:
            return "HIGH"
        if v >= 40:
            return "MEDIUM"
        return "LOW"
    if key in {"orders_delta_pct", "revenue_delta_pct"}:
        if v <= -30:
            return "HIGH"
        if v <= -10:
            return "MEDIUM"
        return "LOW"
    return "MEDIUM"


def _confidence_from_payload(item: dict, payload: dict[str, object]) -> str:
    explicit = str(item.get("confidence") or "").lower()
    completeness = 0
    for key in ["title", "context", "outcome", "impact_mechanism", "delay_cost"]:
        if _safe(payload.get(key)):
            completeness += 1
    if payload.get("items"):
        completeness += 1
    if explicit == "high" and completeness >= 6:
        return "HIGH"
    if explicit in {"high", "medium"} and completeness >= 5:
        return "MEDIUM"
    return "LOW"


def _priority_justification(tier_label: str, value: float, delay_cost: str) -> str:
    rank = str(tier_label).replace("Action ", "").replace("#", "")
    if rank.startswith("1"):
        return f"Highest impact action by value ({_format_currency(value)}) with immediate decay ({delay_cost})."
    return f"Lower impact than Action #1 ({_format_currency(value)}), but still time-sensitive at {delay_cost}."


def _priority_justification_safe(action_idx: int, values: list[float], delay_cost: str) -> str:
    current = values[action_idx] if 0 <= action_idx < len(values) else 0.0
    max_value = max(values) if values else 0.0
    gap_score = ((current / max_value) * 100.0) if max_value > 0 else 0.0
    return (
        f"Priority score {gap_score:.1f}/100 from normalized impact {_format_currency(current)}; "
        f"current decay cost {delay_cost}."
    )


def _action_class(kind: str) -> str:
    mapping = {
        "churn": "retention_recovery",
        "return": "cost_control",
        "concentration": "structural_risk",
        "out_of_stock": "liquidity_recovery",
        "dead_inventory": "liquidity_recovery",
        "inventory": "liquidity_recovery",
        "general": "structural_risk",
    }
    return mapping.get(kind, "structural_risk")


def _confidence_tone(confidence: str) -> tuple[str, str]:
    _ = confidence
    return "Expected to produce:", "deterministic"


def _apply_confidence_to_mechanism(text: str, confidence: str) -> str:
    _ = confidence
    return text


def _build_action_payload(item: dict, summary: dict) -> dict[str, object]:
    kind = _action_kind(item)
    metrics = _action_priority_metrics(item)
    value = metrics["recoverable"]
    minutes = int(item.get("time_required_minutes") or 15)
    daily_loss = metrics["daily_loss"]
    priority_score = metrics["priority_score"]
    daily_loss_label = f"{_format_currency(daily_loss)}/day"

    if kind == "churn":
        items = _churn_items(summary)
        listed = len(items)
        title = "Recover churned customers via 48h 10% offer"
        context = f"{listed} customers are inactive for more than 90 days." if listed > 0 else ""
        target_orders = max(1, min(3, listed))
        execution = "Send a 10% win-back offer to customers inactive for 90+ days."
        outcome = f"+1-2 reactivation orders (baseline 0 -> target 1-2)" if listed > 0 else ""
        profile = _action_class(kind)
    elif kind == "return":
        items = _return_items(summary)
        top = (summary.get("revenue", {}).get("high_return_rate", []) or [{}])[0]
        rate = _to_float_optional(top.get("return_rate"))
        name = _clean_entity_name(top.get("product_title"))
        title = f"Pause ads for high-return product ({name})" if name else "Pause ads for high-return products"
        context = f"{name} return rate is {rate * 100:.1f}%." if name and rate is not None else ""
        execution = f"Pause paid ads for {name} until return rate improves." if name else ""
        baseline_rate = (rate * 100.0) if rate is not None else None
        target_rate = max((baseline_rate or 0.0) - 5.0, 0.0) if baseline_rate is not None else None
        outcome = (
            f"-5.0pp return rate (baseline {baseline_rate:.1f}% -> target {target_rate:.1f}%)"
            if target_rate is not None
            else ""
        )
        profile = _action_class(kind)
    elif kind == "concentration":
        items = _concentration_items(summary)
        pct = _to_float_optional(_business_snapshot(summary).get("concentration_risk_pct"))
        listed = len(items)
        title = "Reduce revenue concentration risk from top customers"
        context = f"Top 2 customers represent {pct:.1f}% of loyal revenue." if pct is not None else ""
        target_customers = max(1, min(3, listed))
        execution = "Send a repeat-order offer to loyal customers outside your current top 2 buyers."
        target_pct = max((pct or 0.0) - 10.0, 0.0) if pct is not None else None
        outcome = (
            f"+{target_customers} repeat orders (baseline 0 -> target {target_customers})"
            if listed > 0
            else ""
        )
        if pct is not None and target_pct is not None:
            outcome = f"Reduce top-2 customer concentration by 10 percentage points (baseline {pct:.1f}% -> target {target_pct:.1f}%)"
        profile = _action_class(kind)
    elif kind == "out_of_stock":
        items = _inventory_items(summary)
        oos = len(summary.get("inventory", {}).get("out_of_stock", []) or [])
        listed = len(items)
        title = "Restock out-of-stock variants to recover blocked sales"
        context = f"{oos} variants are currently at zero inventory." if oos > 0 else ""
        execution = "Restock the flagged out-of-stock variants first to recover blocked sales."
        target_oos = max(oos - listed, 0)
        outcome = f"-{listed} out-of-stock variants (baseline {oos} -> target {target_oos})" if listed > 0 else ""
        profile = _action_class(kind)
    elif kind == "dead_inventory":
        items = _dead_inventory_items(summary)
        listed = len(items)
        title = "Clear dead inventory via discount and bundling"
        context = f"{listed} SKUs have inventory >0 and zero sales in the last 90 days." if listed > 0 else ""
        execution = "Create automatic discount (15%) and bundle offer for listed SKUs."
        outcome = "+1-2 SKUs with first sale (baseline 0 -> target 1-2)" if listed > 0 else ""
        profile = _action_class(kind)
    elif kind == "inventory":
        # Inventory insight defaults to out-of-stock taxonomy for strict separation.
        items = _inventory_items(summary)
        listed = len(items)
        title = "Restock out-of-stock variants to recover blocked sales"
        context = f"{listed} variants are currently at zero inventory." if listed > 0 else ""
        execution = "Restock the flagged out-of-stock variants first to recover blocked sales."
        outcome = f"-{listed} out-of-stock variants (baseline {listed} -> target 0)" if listed > 0 else ""
        profile = _action_class(kind)
    else:
        return {}

    context = _safe_render_text(context, max_len=170)
    outcome = _safe_render_text(outcome, max_len=170)
    execution = _safe_render_text(execution, max_len=170)
    items = [x for x in items if _safe_render_text(x)]
    return {
        "title": title,
        "recoverable_value": value,
        "value_label": _money_label(item),
        "minutes_txt": f"{minutes} min",
        "daily_loss_label": daily_loss_label,
        "daily_loss_value": daily_loss,
        "priority_score": priority_score,
        "context": context,
        "items": items,
        "execution": execution,
        "outcome": outcome,
        "profile": profile,
    }


def _to_number(value: object) -> float | int:
    iv = _to_int_optional(value)
    if iv is not None and abs(float(iv) - _to_float(value)) < 0.000001:
        return iv
    return round(_to_float(value), 2)


def _expected_result_struct(kind: str, payload: dict[str, object], summary: dict) -> dict[str, object]:
    if kind == "churn":
        return {"baseline": 0, "target_min": 1, "target_max": 2, "metric": "reactivation_orders"}
    if kind == "return":
        top = (summary.get("revenue", {}).get("high_return_rate", []) or [{}])[0]
        baseline_rate = _to_float_optional(top.get("return_rate"))
        if baseline_rate is None:
            baseline_rate = 0.0
        baseline_pct = round(baseline_rate * 100.0, 1)
        return {
            "baseline": baseline_pct,
            "target_min": max(round(baseline_pct - 7.0, 1), 0.0),
            "target_max": max(round(baseline_pct - 5.0, 1), 0.0),
            "metric": "return_rate_pct",
        }
    if kind == "concentration":
        concentration = _to_float_optional(_business_snapshot(summary).get("revenue_concentration"))
        base = round(concentration or 0.0, 2)
        return {"baseline": base, "target_min": max(base - 12.0, 0.0), "target_max": max(base - 8.0, 0.0), "metric": "top2_revenue_share_pct"}
    if kind == "out_of_stock":
        oos = len(summary.get("inventory", {}).get("out_of_stock", []) or [])
        target_min = max(oos - 2, 0)
        target_max = max(oos - 1, 0)
        return {"baseline": oos, "target_min": target_min, "target_max": target_max, "metric": "out_of_stock_variants"}
    if kind == "dead_inventory":
        return {"baseline": 0, "target_min": 1, "target_max": 2, "metric": "first_sale_skus"}
    return {"baseline": 0, "target_min": 0, "target_max": 0, "metric": "unknown"}


def _action_id(kind: str, rank: int) -> str:
    return f"{kind}-{rank}"


def build_structured_actions(summary: dict, *, max_actions: int = 5) -> list[dict[str, object]]:
    insights = list(summary.get("insights", []) or [])
    ranked_actions = _rank_priority_actions(insights, max_actions=max_actions)
    structured: list[dict[str, object]] = []
    for idx, item in enumerate(ranked_actions, start=1):
        kind = _action_kind(item)
        payload = _build_action_payload(item, summary)
        title = _safe(payload.get("title"))
        context = _safe(payload.get("context"))
        execution = _safe(payload.get("execution"))
        targets = [t for t in (payload.get("items") or []) if _safe(t)]
        if not title or not context or not execution or not targets:
            continue
        value = _to_float(payload.get("recoverable_value"))
        daily_loss = _to_float(payload.get("daily_loss_value"))
        priority_score = round(value + (daily_loss * 7.0), 2)
        expected_result = _expected_result_struct(kind, payload, summary)
        goal_line = (
            f"Target: {expected_result.get('target_min')}-{expected_result.get('target_max')} "
            f"{_safe(expected_result.get('metric')).replace('_', ' ')} in 7 days"
        )
        structured.append(
            {
                "id": _action_id(kind, idx),
                "title": _strip_weak_language(title),
                "value": round(value, 2),
                "daily_loss": round(daily_loss, 2),
                "priority_score": priority_score,
                "rank": idx,
                "context": _strip_weak_language(context),
                "targets": targets,
                "execute_command": _strip_weak_language(execution),
                "goal": goal_line,
                "measured_by": ["orders_7d", "revenue_7d"],
                "impact_score_label": f"Impact Score: {int(round(priority_score, 0))} (Value + 7-day loss)",
                "expected_result": {
                    "baseline": _to_number(expected_result.get("baseline")),
                    "target_min": _to_number(expected_result.get("target_min")),
                    "target_max": _to_number(expected_result.get("target_max")),
                    "metric": _safe(expected_result.get("metric")),
                },
            }
        )
    structured.sort(key=lambda x: (-_to_float(x.get("priority_score")), str(x.get("id"))))
    for rank, action in enumerate(structured, start=1):
        action["rank"] = rank
        action["id"] = _action_id(_action_kind({"title": action.get("title")}), rank)
    return structured


def _financial_context_line(item: dict, exact_items: list[object]) -> str:
    title = str(item.get("title") or "").lower()
    problem = _safe(item.get("problem"))
    entities = [_clean_entity_name(x) for x in (exact_items or []) if _clean_entity_name(x)]
    entity = entities[0] if entities else "named entity"
    pct = _extract_percent(problem)
    count = _extract_count(problem)

    if "churn" in title:
        if count is not None:
            return f"{count} customers are inactive beyond the 90-day threshold."
        return "Customers crossed the 90-day inactivity threshold."
    if "return" in title:
        if pct is not None:
            return f"{entity} is flagged with a {pct:.1f}% return rate above policy threshold."
        return f"{entity} is flagged by the return-rate threshold rule."
    if "concentration" in title:
        if pct is not None:
            return f"Top customers account for {pct:.1f}% of loyal revenue concentration."
        return "Top-customer concentration rule triggered from loyal revenue mix."
    if "inventory" in title or "dead inventory" in title:
        if count is not None:
            return f"{count} inventory units or variants are stalled beyond sell-through threshold."
        return "Inventory sell-through threshold is not met for flagged items."
    if problem:
        clean_problem = re.sub(r"\$?\d[\d,]*(\.\d+)?", "", problem)
        return _safe_render_text(clean_problem, max_len=170)
    return f"Threshold rule triggered for {entity}."


def _financial_outcome_line(item: dict) -> str:
    title = str(item.get("title") or "").lower()
    if "churn" in title:
        return "Increase reactivation orders from the inactive customer cohort."
    if "return" in title:
        return "Lower returns-driven margin loss on the flagged product."
    if "concentration" in title:
        return "Lower top-customer revenue concentration in the next reporting cycle."
    if "inventory" in title or "dead inventory" in title:
        return "Increase sell-through on flagged inventory in the next cycle."
    if str(item.get("impact_type") or "").lower() == "risk":
        return "Reduce near-term revenue downside from the flagged condition."
    return "Recover incremental revenue from this action in the next cycle."


def _meaningful_items(items: list[object], max_items: int = 4) -> list[str]:
    cleaned: list[str] = []
    for raw in items or []:
        text = _safe(raw)
        if not text:
            continue
        lowered = text.lower()
        if lowered in {"unknown", "n/a", "none", "-", "default", "store"}:
            continue
        if "sku -" in lowered or "unknown" in lowered:
            continue
        if _has_broken_placeholder(text):
            continue
        entity = _clean_entity_name(text)
        if not entity:
            continue
        cleaned.append(entity)
    cleaned = list(dict.fromkeys(cleaned))
    return cleaned[:max_items]


def _decision_stack(insights: list[dict]) -> dict[str, list[dict]]:
    # Premium output rule: only surface actions with concrete dollar values.
    ranked = [i for i in _prioritize_insights(insights) if _to_float(i.get("potential_value")) > 0]
    must: list[dict] = []
    should: list[dict] = []
    optional: list[dict] = []
    for i in ranked:
        title = str(i.get("title") or "").strip()
        if not title:
            continue
        if not must:
            must.append(i)
            continue
        if len(should) < 2:
            should.append(i)
            continue
        if len(optional) < 2:
            optional.append(i)
        if len(optional) >= 2:
            break
    return {"must": must, "should": should, "optional": optional}


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


def _clean_sentence(value: object, fallback: str = "") -> str:
    text = _safe(value)
    if not text:
        return fallback
    text = text.rstrip(" .")
    return f"{text}."


def _snapshot_table_rows(snapshot: dict) -> list[list[str]]:
    rows: list[list[str]] = [["Metric", "Value"]]
    cur_rev = _to_float_optional(snapshot.get("current_7d_net_revenue"))
    prev_rev = _to_float_optional(snapshot.get("previous_7d_net_revenue"))
    if cur_rev is not None and prev_rev is not None:
        if cur_rev == 0 and prev_rev == 0:
            rows.append(["Revenue momentum", "No revenue activity"])
        else:
            rows.append(["Revenue momentum", f"{_format_currency(cur_rev)} vs {_format_currency(prev_rev)}"])
    else:
        rows.append(["Revenue momentum", "Not available"])
    orders = snapshot.get("current_7d_orders")
    rows.append(["Orders", str(int(orders)) if orders is not None else "Not available"])
    inactive = snapshot.get("churn_risk_count")
    rows.append(["Inactive customers", str(int(inactive)) if inactive is not None else "Not available"])
    inventory_pressure = snapshot.get("inventory_risk_count")
    rows.append(["Inventory pressure", str(int(inventory_pressure)) if inventory_pressure is not None else "Not available"])
    concentration = snapshot.get("concentration_risk_pct")
    rows.append(["Revenue concentration", _format_percent(concentration) if concentration is not None else "Not available"])
    return rows


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
    current_7d = _to_int_optional(trend.get("current_7d_orders"))
    previous_7d = _to_int_optional(trend.get("previous_7d_orders"))
    delta = (current_7d - previous_7d) if current_7d is not None and previous_7d is not None else None
    delta_pct = (delta / previous_7d * 100.0) if delta is not None and previous_7d and previous_7d > 0 else None

    current_7d_net = _to_float_optional(trend.get("current_7d_net_revenue"))
    previous_7d_net = _to_float_optional(trend.get("previous_7d_net_revenue"))
    delta_net = (current_7d_net - previous_7d_net) if current_7d_net is not None and previous_7d_net is not None else None
    delta_net_pct = (delta_net / previous_7d_net * 100.0) if delta_net is not None and previous_7d_net and previous_7d_net > 0 else None
    churn_list = customers.get("churned")
    churn_risk = len(churn_list) if isinstance(churn_list, list) else None
    out_of_stock = inventory.get("out_of_stock")
    critical_stock = inventory.get("critical_stock")
    inventory_risk = (len(out_of_stock) if isinstance(out_of_stock, list) else 0) + (len(critical_stock) if isinstance(critical_stock, list) else 0)
    if not isinstance(out_of_stock, list) and not isinstance(critical_stock, list):
        inventory_risk = None
    loyal = customers.get("loyal")
    concentration_risk = None
    if isinstance(loyal, list):
        loyal_revenue = sum(_to_float(c.get("total_spent")) for c in loyal)
        top2_revenue = sum(_to_float(c.get("total_spent")) for c in loyal[:2])
        if loyal_revenue > 0:
            concentration_risk = (top2_revenue / loyal_revenue * 100.0)
    if inventory_risk is None:
        inventory_risk = 0
    concentration_risk = round(_to_float(concentration_risk), 2)
    momentum = _render_revenue_trend_line(
        {
            "current_7d_net_revenue": current_7d_net,
            "previous_7d_net_revenue": previous_7d_net,
        }
    )
    rev_delta = _to_float(delta_net_pct)
    if inventory_risk >= 20 or concentration_risk >= 70 or rev_delta <= -20:
        status = "Critical"
    elif inventory_risk >= 8 or concentration_risk >= 40 or rev_delta < 0:
        status = "Warning"
    else:
        status = "Stable"
    return {
        "store_status": status,
        "revenue_momentum": momentum or "No revenue activity in the last 7 days",
        "inventory_pressure": int(inventory_risk),
        "revenue_concentration": concentration_risk,
        "inventory_risk_count": int(inventory_risk),
        "concentration_risk_pct": concentration_risk,
        "current_7d_orders": current_7d,
        "previous_7d_orders": previous_7d,
        "delta_orders": delta,
        "delta_pct": delta_pct,
        "current_7d_net_revenue": current_7d_net,
        "previous_7d_net_revenue": previous_7d_net,
        "delta_7d_net_revenue": delta_net,
        "delta_7d_net_revenue_pct": delta_net_pct,
        "churn_risk_count": churn_risk,
    }


def get_business_health_snapshot(summary: dict) -> dict[str, object]:
    raw = _business_snapshot(summary)
    return {
        "store_status": raw.get("store_status", "Stable"),
        "revenue_momentum": _safe(raw.get("revenue_momentum")),
        "inventory_pressure": int(_to_int_optional(raw.get("inventory_pressure")) or 0),
        "revenue_concentration": round(_to_float(raw.get("revenue_concentration")), 2),
    }


def _render_revenue_trend_line(snapshot: dict) -> str:
    cur = snapshot.get("current_7d_net_revenue")
    prev = snapshot.get("previous_7d_net_revenue")
    if cur is None or prev is None:
        return ""
    if cur <= 0 and prev <= 0:
        return "No revenue activity in the last 7 days"
    if prev <= 0 and cur > 0:
        return f"{_format_currency(cur)} in the last 7 days (no prior-week baseline)"
    # prev > 0
    delta = cur - prev
    pct = (delta / prev * 100.0) if prev > 0 else None
    if pct is None:
        direction = "up" if delta >= 0 else "down"
        return f"{_format_currency(cur)} vs {_format_currency(prev)} ({direction} {_format_currency(abs(delta))})"
    direction = "up" if pct >= 0 else "down"
    return f"{_format_currency(cur)} vs {_format_currency(prev)} ({direction} {abs(pct):.2f}%)"


def _business_health_status(snapshot: dict) -> str:
    inventory_risk = _to_int_optional(snapshot.get("inventory_risk_count")) or 0
    concentration = _to_float_optional(snapshot.get("concentration_risk_pct")) or 0.0
    rev_delta_pct = _to_float_optional(snapshot.get("delta_7d_net_revenue_pct")) or 0.0
    critical_signals = 0
    if inventory_risk >= 20:
        critical_signals += 1
    if concentration >= 70:
        critical_signals += 1
    if rev_delta_pct <= -20:
        critical_signals += 1
    if critical_signals >= 2:
        return "Needs immediate attention"
    if inventory_risk >= 8 or concentration >= 40 or rev_delta_pct < 0:
        return "Needs monitoring"
    return "Healthy"


def _risk_summary_line(snapshot: dict) -> str:
    inventory_risk = _to_int_optional(snapshot.get("inventory_risk_count")) or 0
    concentration = _to_float_optional(snapshot.get("concentration_risk_pct")) or 0.0
    rev_delta_pct = _to_float_optional(snapshot.get("delta_7d_net_revenue_pct")) or 0.0
    if inventory_risk >= 20 and concentration >= 70:
        return "High stockout volume and concentrated revenue increase downside risk."
    if rev_delta_pct < 0:
        return "Revenue decline with operational pressure requires immediate corrective action."
    return "Risk is contained across revenue concentration and inventory exposure."


def create_report_pdf(summary: dict, output_dir: str = "reports", task_sections: dict | None = None, *, store_id: int) -> str:
    style = _styles()
    generated_at = datetime.now(timezone.utc)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / f"store-intelligence-store-{store_id}-{generated_at.strftime('%Y%m%d-%H%M%S')}.pdf"

    snapshot = _business_snapshot(summary)
    insights = list(summary.get("insights", []) or [])
    ranked_actions = _rank_priority_actions(insights, max_actions=5)
    totals = _financial_summary(ranked_actions)
    structured_actions = build_structured_actions(summary, max_actions=5)

    story = [Paragraph("Store Intelligence Report", style["title"]), Paragraph(f"Generated {generated_at.strftime('%Y-%m-%d %H:%M UTC')}", style["meta"])]

    rendered_sections: set[str] = set()

    def _append_section_once(section_title: str, color: str) -> bool:
        if section_title in rendered_sections:
            return False
        rendered_sections.add(section_title)
        story.append(_section_header(section_title, style, color))
        return True

    _append_section_once("EXECUTIVE SUMMARY", "#101828")
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"Total Recoverable Revenue: {_format_currency(totals['recoverable'])}", style["body"]))
    story.append(Paragraph(f"Total Risk Exposure: {_format_currency(totals['risk'])}", style["body"]))

    story.append(Spacer(1, 12))
    _append_section_once("PRIORITY ACTIONS", "#7A271A")
    story.append(Spacer(1, 6))

    def _render_action(action: dict) -> bool:
        story.append(Paragraph(f"<b>ACTION #{int(action['rank'])} — {_clean_sentence(action['title']).rstrip('.')}</b>", style["action_title"]))
        story.append(Spacer(1, 2))
        story.append(Paragraph(f"<b>Value:</b> {_format_currency(_to_float(action['value']))} recoverable", style["action_label"]))
        story.append(Paragraph(f"<b>Daily Loss:</b> {_format_currency(_to_float(action['daily_loss']))}/day", style["action_label"]))
        story.append(Paragraph(f"<b>Impact Score:</b> {int(round(_to_float(action['priority_score']), 0))} (Value + 7-day loss)", style["action_label"]))
        story.append(Paragraph(f"<b>Score Formula:</b> {_PRIORITY_FORMULA}", style["action_label"]))
        story.append(Spacer(1, 2))
        if action["context"]:
            story.append(Paragraph(f"<b>Context:</b> {_clean_sentence(action['context'])}", style["action_note"]))
        if action["targets"]:
            story.append(Paragraph("<b>Targets:</b>", style["action_label"]))
            story.append(Paragraph(_soft_bullets(action["targets"], 4), style["muted"]))
        if action["execute_command"]:
            story.append(Paragraph("<b>EXECUTE:</b>", style["action_label"]))
            story.append(Paragraph(_clean_sentence(action["execute_command"]), style["action_note"]))
        story.append(Paragraph(f"<b>Goal:</b> {_clean_sentence(action['goal'])}", style["action_note"]))
        story.append(Paragraph(f"<b>Measured by:</b> {', '.join(action['measured_by'])}", style["action_note"]))
        er = action["expected_result"]
        if er:
            story.append(Paragraph("<b>Expected Result:</b>", style["action_label"]))
            story.append(
                Paragraph(
                    _clean_sentence(
                        f"{er['metric']}: baseline {er['baseline']} -> target {er['target_min']}-{er['target_max']}"
                    ),
                    style["action_note"],
                )
            )
        story.append(Spacer(1, 12))
        return True

    rendered_actions = 0
    for action in structured_actions:
        if _render_action(action):
            rendered_actions += 1
    if rendered_actions == 0:
        story.append(Paragraph("No executable Shopify actions met the daily profit criteria.", style["muted"]))

    story.append(Spacer(1, 12))
    _append_section_once("BUSINESS HEALTH SNAPSHOT", "#1D2939")
    story.append(Spacer(1, 6))
    health = get_business_health_snapshot(summary)
    story.append(Paragraph(f"Store Status: {health['store_status']}", style["body"]))
    story.append(Paragraph(f"Revenue Momentum: {health['revenue_momentum']}", style["body"]))
    story.append(Paragraph(f"Inventory Pressure: {int(health['inventory_pressure'])}", style["body"]))
    story.append(Paragraph(f"Revenue Concentration: {float(health['revenue_concentration']):.2f}", style["body"]))

    story.append(Spacer(1, 12))
    _append_section_once("EXECUTION ORDER", "#101828")
    story.append(Spacer(1, 6))
    story.append(Paragraph("Actions are already sorted by business impact. Execute them in numeric order: Action #1, then #2, then #3.", style["body"]))

    doc = SimpleDocTemplate(str(output_path), pagesize=LETTER, leftMargin=40, rightMargin=40, topMargin=40, bottomMargin=40, title="Store Intelligence Report", author="Shopify Automation Pipeline")
    doc.build(story)
    logger.info("PDF report written to %s", output_path)
    return str(output_path)
