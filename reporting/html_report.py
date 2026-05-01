from __future__ import annotations

from html import escape

from reporting.advice_engine import get_action_advice


def _fmt_money(value: float | int | None) -> str:
    try:
        return f"${float(value or 0.0):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


def _status_badge(status: str) -> tuple[str, str, str]:
    normalized = str(status or "").strip().lower()
    if normalized == "healthy":
        return ("HEALTHY", "#00e5a0", "#0d2b1f")
    if normalized == "critical":
        return ("CRITICAL", "#ff4444", "#2b0000")
    return ("WARNING", "#ff6b35", "#2b1a00")


def _state_badge(state: str) -> str:
    normalized = str(state or "PENDING").strip().upper()
    return (
        "<span style=\"display:inline-block; padding:3px 10px; border-radius:20px; "
        "background-color:#1a1a1a; color:#555555; border:1px solid #333333; font-size:11px; font-weight:700; letter-spacing:0.3px;\">"
        f"{escape(normalized)}"
        "</span>"
    )


def _daily_impact_badge(value: float) -> str:
    return (
        "<span style=\"display:inline-block; padding:6px 12px; border-radius:999px; "
        "background-color:#0d2b1f; border:1px solid #00e5a0; color:#00e5a0; font-size:13px; font-weight:700;\">"
        f"{escape(_fmt_money(value))}/day"
        "</span>"
    )


def _render_playbook(items: list[str]) -> str:
    if not items:
        return "<p style=\"color:#00e5a0; font-size:13px; margin:0 0 8px 0;\">→ No specific playbook steps available.</p>"
    return "".join(
        f"<p style=\"color:#00e5a0; font-size:13px; margin:0 0 8px 0;\">→ {escape(str(item))}</p>"
        for item in items
    )


def _safe_text(value: object, *, default: str = "—") -> str:
    text = str(value).strip() if value is not None else ""
    if not text or text.lower() in {"n/a", "none", "n/a - not relevant"}:
        return default
    return text


def _render_targets(targets: list[dict], action_type: str) -> str:
    normalized_type = str(action_type or "").strip().lower()
    if normalized_type in {"low_repeat_purchase_rate", "abandoned_checkout_spike"}:
        return ""
    if not targets:
        return (
            "<tr><td style=\"color:#666666; font-family:ui-monospace, SFMono-Regular, Menlo, monospace; "
            "font-size:12px;\">—</td></tr>"
        )

    rows: list[str] = []
    for t in targets:
        name = escape(_safe_text(t.get("name")))
        sku = escape(_safe_text(t.get("sku")))
        inventory = _safe_text(t.get("inventory"))
        sales_90d = _safe_text(t.get("sales_last_90d"))
        rr_raw = t.get("return_rate")
        returned_units = t.get("returned_units")
        email = escape(_safe_text(t.get("email")))
        ltv = t.get("ltv")
        days_since_order = _safe_text(t.get("days_since_order"))
        price = _safe_text(t.get("price"))
        units_sold = _safe_text(t.get("units_sold"))

        if normalized_type == "dead_inventory":
            detail = f"<span style=\"color:#666666;\"> | INV: {escape(inventory)} | 90D SALES: {escape(sales_90d)}</span>"
            lead = sku if sku != "—" else name
        elif normalized_type == "high_return_rate":
            rr_text = "—"
            if rr_raw is not None:
                try:
                    rr_text = f"{float(rr_raw):.1f}%"
                except (TypeError, ValueError):
                    rr_text = "—"
            units_text = "—"
            if returned_units is not None:
                try:
                    units = int(returned_units)
                    units_text = f"{units} unit returned" if units == 1 else f"{units} units returned"
                except (TypeError, ValueError):
                    units_text = "—"
            detail = f"<span style=\"color:#666666;\"> | RETURN RATE: {escape(rr_text)} | {escape(units_text)}</span>"
            lead = name
        elif normalized_type == "churned_customers":
            detail = f"<span style=\"color:#666666;\"> | LAST ORDER: {escape(days_since_order)} days ago</span>"
            lead = email if email != "—" else name
        elif normalized_type == "high_value_customer_at_risk":
            ltv_text = "—"
            if ltv is not None:
                try:
                    ltv_text = f"${float(ltv):,.2f}"
                except (TypeError, ValueError):
                    ltv_text = "—"
            detail = f"<span style=\"color:#666666;\"> | LTV: {escape(ltv_text)} | SILENT: {escape(days_since_order)} days</span>"
            lead = name
        elif normalized_type == "low_margin_products":
            price_text = "—"
            try:
                if str(price) != "—":
                    price_text = f"${float(price):,.2f}"
            except (TypeError, ValueError):
                price_text = "—"
            detail = f"<span style=\"color:#666666;\"> | PRICE: {escape(price_text)} | UNITS SOLD: {escape(units_sold)}</span>"
            lead = sku if sku != "—" else name
        else:
            # Generic fallback: avoid N/A/None and only show meaningful fields.
            parts = []
            lead = sku if sku != "—" else name
            if str(inventory) != "—":
                parts.append(f"INV: {escape(inventory)}")
            if str(sales_90d) != "—":
                parts.append(f"90D SALES: {escape(sales_90d)}")
            if parts:
                detail = f"<span style=\"color:#666666;\"> | {' | '.join(parts)}</span>"
            else:
                detail = ""

        rows.append(
            "<tr>"
            "<td style=\"padding:0 0 3px 0;\">"
            "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\" style=\"background-color:#0f0f0f; border-radius:3px;\">"
            "<tr><td style=\"padding:6px 10px; font-family:'Courier New', Courier, monospace; font-size:12px; line-height:1.4;\">"
            f"<span style=\"color:#00e5a0;\">{lead}</span>"
            f"{detail}"
            "</td></tr></table>"
            "</td>"
            "</tr>"
        )
    return "".join(rows)


def build_html_report(report_data: dict) -> str:
    store_name = escape(str(report_data.get("store_name") or "Store Intelligence"))
    date_text = escape(str(report_data.get("date") or ""))
    status_label, status_fg, status_bg = _status_badge(str(report_data.get("status") or "warning"))

    daily_impact = _fmt_money(report_data.get("daily_impact"))
    total_value = _fmt_money(report_data.get("total_value"))
    projection = _fmt_money(report_data.get("seven_day_projection"))
    execute_value = _fmt_money(report_data.get("execute_value"))
    ignore_loss = _fmt_money(report_data.get("ignore_loss"))
    delta = _fmt_money(report_data.get("delta"))
    delta_raw = float(report_data.get("delta") or 0.0)
    delta_color = "#00e5a0" if delta_raw >= 0 else "#ff6b35"
    root_cause = escape(str(report_data.get("root_cause") or "OPERATIONAL REVENUE LEAK"))

    actions = list(report_data.get("actions") or [])
    action_blocks: list[str] = []
    for action in actions:
        number = escape(str(action.get("number") or ""))
        action_type = escape(_safe_text(action.get("type"), default="ACTION"))
        action_type_raw = str(action.get("action_type") or "").strip().lower()
        is_primary = "PRIMARY" in action_type.upper()
        border_color = "#00e5a0" if is_primary else "#ff6b35"
        action_daily = float(action.get("daily_impact") or 0.0)
        state = _state_badge(str(action.get("state") or "PENDING"))
        target_rows = _render_targets(list(action.get("targets") or []), action_type_raw)
        advice = get_action_advice(
            str(action.get("action_type") or action.get("type") or ""),
            dict(action.get("metrics") or {}),
        )
        advice_headline = escape(str(advice.get("headline") or ""))
        advice_context = escape(str(advice.get("context") or ""))
        advice_benchmark = escape(str(advice.get("benchmark") or ""))
        advice_urgency = escape(str(advice.get("urgency") or ""))
        playbook_html = _render_playbook(list(advice.get("playbook") or []))
        target_section = (
            "<tr><td style=\"padding:0 20px 4px 20px; color:#555555; font-size:10px; text-transform:uppercase; letter-spacing:1px;\">TARGETS</td></tr>"
            f"<tr><td style=\"padding:0 20px 10px 20px;\">"
            "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\">"
            f"{target_rows}"
            "</table></td></tr>"
            if target_rows
            else ""
        )

        action_blocks.append(
            "<tr>"
            "<td style=\"padding:0 0 14px 0;\">"
            "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\" "
            f"style=\"background-color:#141414; border:1px solid #222222; border-left:3px solid {border_color}; border-radius:6px;\">"
            "<tr>"
            "<td style=\"padding:20px;\">"
            "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\">"
            "<tr>"
            "<td style=\"padding:0 10px 0 0;\">"
            f"<div style=\"color:#555555; font-size:11px; letter-spacing:1px; text-transform:uppercase;\">Action {number}</div>"
            f"<div style=\"color:{border_color}; font-size:14px; font-weight:600;\">{action_type}</div>"
            "</td>"
            "<td align=\"right\">"
            f"{_daily_impact_badge(action_daily)}"
            "</td>"
            "</tr>"
            "</table>"
            "</td>"
            "</tr>"
            "<tr><td style=\"padding:0 20px 12px 20px;\">"
            f"<p style=\"color:#ffffff; font-size:15px; font-weight:600; margin:0 0 12px 0;\">{advice_headline}</p>"
            f"<p style=\"color:#a0a0a0; font-size:13px; line-height:1.6; margin:0 0 16px 0;\">{advice_context}</p>"
            "<div style=\"background:#0d2b1f; border-radius:4px; padding:12px 16px; margin-bottom:12px;\">"
            "<p style=\"color:#00e5a0; font-size:10px; letter-spacing:1px; margin:0 0 8px 0;\">WHAT TO DO</p>"
            f"{playbook_html}"
            "</div>"
            f"<p style=\"color:#666666; font-size:12px; font-style:italic; margin:0 0 8px 0;\">{advice_benchmark}</p>"
            "<div style=\"background:#2b0d0d; border-radius:4px; padding:10px 14px;\">"
            f"<p style=\"color:#ff6b35; font-size:12px; margin:0;\">⚠ {advice_urgency}</p>"
            "</div>"
            "</td></tr>"
            f"{target_section}"
            "<tr><td style=\"padding:0 20px 20px 20px;\" align=\"right\">"
            f"{state}"
            "</td></tr>"
            "</table>"
            "</td>"
            "</tr>"
        )

    actions_html = "".join(action_blocks) or (
        "<tr><td style=\"color:#a0a0a0; padding:8px 0 0 0;\">No actions detected for today.</td></tr>"
    )

    return (
        "<!doctype html>"
        "<html><head>"
        "<meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
        "<title>Store Intelligence Report</title>"
        "</head>"
        "<body style=\"margin:0; padding:0; background-color:#0a0a0a; font-family:system-ui, -apple-system, Arial, sans-serif;\">"
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\" style=\"background-color:#0a0a0a;\">"
        "<tr><td align=\"center\" style=\"padding:20px 10px;\">"
        "<table role=\"presentation\" width=\"620\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\" "
        "style=\"width:100%; max-width:620px; background-color:#0a0a0a;\">"
        "<tr><td style=\"padding:0 0 14px 0;\">"
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\">"
        "<tr>"
        f"<td style=\"color:#888888; font-size:13px; text-transform:uppercase; letter-spacing:1px; font-variant:small-caps;\">{store_name}</td>"
        f"<td align=\"right\" style=\"color:#888888; font-size:13px;\">{date_text}</td>"
        "</tr>"
        "<tr><td colspan=\"2\" style=\"padding-top:8px;\"><div style=\"height:1px; background-color:#00e5a0; line-height:1px;\">&nbsp;</div></td></tr>"
        "<tr><td colspan=\"2\" style=\"padding-top:10px;\">"
        f"<span style=\"display:inline-block; padding:5px 12px; border-radius:999px; background-color:{status_bg}; color:{status_fg}; border:1px solid {status_fg}; font-size:11px; font-weight:700; letter-spacing:0.4px;\">{status_label}</span>"
        "</td></tr>"
        "</table>"
        "</td></tr>"
        "<tr><td style=\"padding:14px 0 12px 0;\">"
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\" style=\"background-color:#141414; border:1px solid #222222; border-radius:8px;\">"
        "<tr><td style=\"padding:24px 24px 8px 24px; color:#888888; font-size:12px; text-transform:uppercase; letter-spacing:2px;\">Today's Opportunity</td></tr>"
        "<tr><td style=\"padding:0 24px 8px 24px;\">"
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\">"
        "<tr>"
        "<td width=\"33.33%\" valign=\"top\" style=\"padding:0 10px 0 0;\">"
        "<div style=\"color:#888888; font-size:11px; text-transform:uppercase; letter-spacing:1px; margin-bottom:4px;\">Daily Impact</div>"
        f"<div style=\"color:#00e5a0; font-size:28px; line-height:1.2; font-weight:700;\">{escape(daily_impact)}</div>"
        "</td>"
        "<td width=\"33.33%\" valign=\"top\" style=\"padding:0 10px;\">"
        "<div style=\"color:#888888; font-size:11px; text-transform:uppercase; letter-spacing:1px; margin-bottom:4px;\">Total Value</div>"
        f"<div style=\"color:#00e5a0; font-size:28px; line-height:1.2; font-weight:700;\">{escape(total_value)}</div>"
        "</td>"
        "<td width=\"33.33%\" valign=\"top\" style=\"padding:0 0 0 10px;\">"
        "<div style=\"color:#888888; font-size:11px; text-transform:uppercase; letter-spacing:1px; margin-bottom:4px;\">7-Day Projection</div>"
        f"<div style=\"color:#00e5a0; font-size:28px; line-height:1.2; font-weight:700;\">{escape(projection)}</div>"
        "</td>"
        "</tr>"
        "</table>"
        "</td></tr>"
        f"<tr><td style=\"padding:16px 24px 24px 24px; color:#555555; font-size:12px; font-style:italic;\">Root cause: {root_cause}</td></tr>"
        "</table>"
        "</td></tr>"
        "<tr><td style=\"padding:0 0 12px 0;\">"
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\" style=\"border:1px solid #333333; border-radius:8px;\">"
        "<tr>"
        "<td width=\"50%\" valign=\"top\" style=\"padding:0; background-color:#0d2b1f;\">"
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\">"
        "<tr><td style=\"padding:14px 16px 6px 16px; color:#00e5a0; font-size:11px; font-weight:700; letter-spacing:2px; text-transform:uppercase;\">EXECUTE</td></tr>"
        f"<tr><td style=\"padding:0 16px 6px 16px; color:#00e5a0; font-size:32px; font-weight:800;\">{escape(execute_value)}</td></tr>"
        "<tr><td style=\"padding:0 16px 14px 16px; color:#4a9b7a; font-size:11px;\">recovered if you act today</td></tr>"
        "</table>"
        "</td>"
        "<td width=\"50%\" valign=\"top\" style=\"padding:0; background-color:#2b0d0d;\">"
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\">"
        "<tr><td style=\"padding:14px 16px 6px 16px; color:#ff6b35; font-size:11px; font-weight:700; letter-spacing:2px; text-transform:uppercase;\">IGNORE</td></tr>"
        f"<tr><td style=\"padding:0 16px 6px 16px; color:#ff6b35; font-size:32px; font-weight:800;\">{escape(ignore_loss)}</td></tr>"
        "<tr><td style=\"padding:0 16px 14px 16px; color:#9b4a2a; font-size:11px;\">projected 7-day loss</td></tr>"
        "</table>"
        "</td>"
        "</tr>"
        "<tr><td colspan=\"2\" style=\"padding:10px 12px; background-color:#1a1a1a; text-align:center;\">"
        f"<div style=\"color:{delta_color}; font-size:14px; font-weight:700;\">DELTA: {escape(delta)}</div>"
        "<div style=\"color:#555555; font-size:11px; margin-top:3px;\">You leave this on the table every 7 days you wait</div>"
        "</td></tr>"
        "</table>"
        "</td></tr>"
        f"{actions_html}"
        "<tr><td style=\"padding:8px 0 0 0; border-top:1px solid #1a1a1a;\">"
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\">"
        "<tr><td align=\"center\" style=\"padding:12px 0 4px 0; color:#333333; font-size:11px;\">Store Intelligence Report - Confidential</td></tr>"
        "<tr><td align=\"center\" style=\"padding:0 0 10px 0; font-size:11px;\">"
        "<a href=\"#\" style=\"color:#333333; text-decoration:underline;\">Unsubscribe</a>"
        "</td></tr>"
        "</table>"
        "</td></tr>"
        "</table>"
        "</td></tr>"
        "</table>"
        "</body></html>"
    )
