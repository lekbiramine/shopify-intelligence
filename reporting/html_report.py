from __future__ import annotations

from html import escape
import os
import re

from reporting.advice_engine import get_action_advice


def _fmt_money(value: float | int | None) -> str:
    try:
        return f"${float(value or 0.0):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


def _status_badge(status: str) -> tuple[str, str, str]:
    normalized = str(status or "").strip().lower()
    if normalized == "healthy":
        return ("HEALTHY", "#5C6BFF", "#0D1A2B")
    if normalized == "critical":
        return ("CRITICAL", "#FF6B6B", "#2B0D1A")
    return ("WARNING", "#FFB347", "#1A1A0D")


def _daily_impact_badge(value: float, *, is_primary: bool) -> str:
    bg = "#0D0D2B" if is_primary else "#2B1515"
    fg = "#5C6BFF" if is_primary else "#FF6B6B"
    return (
        "<span style=\"display:inline-block; padding:6px 12px; border-radius:999px; "
        f"background-color:{bg}; border:1px solid {fg}; color:{fg}; font-size:13px; font-weight:700;\">"
        f"{escape(_fmt_money(value))}/day"
        "</span>"
    )


def _render_playbook(items: list[str]) -> str:
    if not items:
        return "<p style=\"color:#5C6BFF; font-size:13px; margin:0 0 8px 0;\">→ No specific playbook steps available.</p>"
    return "".join(
        f"<p style=\"color:#5C6BFF; font-size:13px; margin:0 0 8px 0;\">→ {escape(str(item))}</p>"
        for item in items
    )


def _safe_text(value: object, *, default: str = "—") -> str:
    text = str(value).strip() if value is not None else ""
    if not text or text.lower() in {"n/a", "none", "n/a - not relevant"}:
        return default
    return text


def _minify_email_html(html: str) -> str:
    """
    Keep markup lean to reduce Gmail clipping.
    """
    compact = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    compact = re.sub(r">\s+<", "><", compact)
    compact = re.sub(r"\s{2,}", " ", compact)
    compact = re.sub(r";\s+", ";", compact)
    compact = re.sub(r":\s+", ":", compact)
    compact = re.sub(r",\s+", ",", compact)
    return compact.strip()


def _render_targets(targets: list[dict], action_type: str) -> str:
    normalized_type = str(action_type or "").strip().lower()
    if normalized_type in {"low_repeat_purchase_rate", "abandoned_checkout_spike"}:
        return ""
    if not targets:
        return (
            "<tr><td style=\"color:#555570; font-family:'Courier New', Courier, monospace; "
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
            detail = f"<span style=\"color:#555570;\"> | INV: {escape(inventory)} | 90D SALES: {escape(sales_90d)}</span>"
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
            detail = f"<span style=\"color:#555570;\"> | RETURN RATE: {escape(rr_text)} | {escape(units_text)}</span>"
            lead = name
        elif normalized_type == "churned_customers":
            detail = f"<span style=\"color:#555570;\"> | LAST ORDER: {escape(days_since_order)} days ago</span>"
            lead = email if email != "—" else name
        elif normalized_type == "high_value_customer_at_risk":
            ltv_text = "—"
            if ltv is not None:
                try:
                    ltv_text = f"${float(ltv):,.2f}"
                except (TypeError, ValueError):
                    ltv_text = "—"
            detail = f"<span style=\"color:#555570;\"> | LTV: {escape(ltv_text)} | SILENT: {escape(days_since_order)} days</span>"
            lead = name
        elif normalized_type == "revenue_concentration":
            spend_raw = t.get("total_spent")
            if spend_raw is None:
                spend_raw = ltv
            spend_text = "—"
            if spend_raw is not None:
                try:
                    spend_text = f"${float(spend_raw):,.2f}"
                except (TypeError, ValueError):
                    spend_text = "—"
            oc = t.get("orders_count")
            orders_text = "—"
            if oc is not None:
                try:
                    orders_text = str(int(oc))
                except (TypeError, ValueError):
                    orders_text = "—"
            detail = f"<span style=\"color:#555570;\"> | SPEND: {escape(spend_text)} | ORDERS: {escape(orders_text)}</span>"
            lead = name
        elif normalized_type == "low_margin_products":
            price_text = "—"
            try:
                if str(price) != "—":
                    price_text = f"${float(price):,.2f}"
            except (TypeError, ValueError):
                price_text = "—"
            detail = f"<span style=\"color:#555570;\"> | PRICE: {escape(price_text)} | UNITS SOLD: {escape(units_sold)}</span>"
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
                detail = f"<span style=\"color:#555570;\"> | {' | '.join(parts)}</span>"
            else:
                detail = ""

        rows.append(
            "<tr>"
            "<td style=\"padding:0 0 3px 0;\">"
            "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\" style=\"background-color:#0A0A14; border-radius:3px;\">"
            "<tr><td style=\"padding:6px 10px; font-family:'Courier New', Courier, monospace; font-size:12px; line-height:1.4;\">"
            f"<span style=\"color:#7B88FF;\">{lead}</span>"
            f"{detail}"
            "</td></tr></table>"
            "</td>"
            "</tr>"
        )
    return "".join(rows)


def build_html_report(report_data: dict, *, unsubscribe_url: str | None = None) -> str:
    store_name = escape(str(report_data.get("store_name") or "Perspicor"))
    date_text = escape(str(report_data.get("date") or ""))
    status_label, status_fg, status_bg = _status_badge(str(report_data.get("status") or "warning"))
    logo_src = (os.getenv("PERSPICOR_LOGO_URL") or "").strip() or "https://perspicor.com/logo/perspicor-dark.png"
    footer_logo_html = (
        f"<img src=\"{escape(logo_src, quote=True)}\" alt=\"Perspicor\" "
        "style=\"display:block; margin:0 auto; height:28px; width:auto;\" />"
        if logo_src
        else "<div style=\"color:#141423; font-size:18px; font-weight:700; letter-spacing:0.3px;\">Perspicor</div>"
    )

    daily_impact = _fmt_money(report_data.get("daily_impact"))
    total_value = _fmt_money(report_data.get("total_value"))
    projection = _fmt_money(report_data.get("seven_day_projection"))
    execute_value = _fmt_money(report_data.get("execute_value"))
    ignore_loss = _fmt_money(report_data.get("ignore_loss"))
    delta = _fmt_money(report_data.get("delta"))
    root_cause = escape(str(report_data.get("root_cause") or "OPERATIONAL REVENUE LEAK"))

    actions = list(report_data.get("actions") or [])
    action_blocks: list[str] = []
    for action in actions:
        number = escape(str(action.get("number") or ""))
        action_type = escape(_safe_text(action.get("type"), default="ACTION"))
        action_type_raw = str(action.get("action_type") or "").strip().lower()
        is_primary = "PRIMARY" in action_type.upper()
        border_color = "#5C6BFF" if is_primary else "#FF6B6B"
        action_daily = float(action.get("daily_impact") or 0.0)
        target_rows = _render_targets(list(action.get("targets") or []), action_type_raw)
        advice = get_action_advice(
            str(action.get("action_type") or action.get("type") or ""),
            dict(action.get("metrics") or {}),
        )
        headline_override = action.get("advice_headline_override")
        context_override = action.get("advice_context_override")
        advice_headline = escape(str(headline_override or advice.get("headline") or ""))
        advice_context = escape(str(context_override or advice.get("context") or ""))
        advice_benchmark = escape(str(advice.get("benchmark") or ""))
        advice_urgency = escape(str(advice.get("urgency") or ""))
        playbook_html = _render_playbook(list(advice.get("playbook") or []))
        target_section = (
            "<tr><td style=\"padding:0 20px 4px 20px; color:#8888AA; font-size:10px; text-transform:uppercase; letter-spacing:1px;\">TARGETS</td></tr>"
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
            f"style=\"background-color:#12121E; border:1px solid #1E1E35; border-left:3px solid {border_color}; border-radius:6px;\">"
            "<tr>"
            "<td style=\"padding:20px;\">"
            "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\">"
            "<tr>"
            "<td style=\"padding:0 10px 0 0;\">"
            f"<div style=\"color:#555570; font-size:11px; letter-spacing:1px; text-transform:uppercase;\">Action {number}</div>"
            f"<div style=\"color:{border_color}; font-size:14px; font-weight:600;\">{action_type}</div>"
            "</td>"
            "<td align=\"right\">"
            f"{_daily_impact_badge(action_daily, is_primary=is_primary)}"
            "</td>"
            "</tr>"
            "</table>"
            "</td>"
            "</tr>"
            "<tr><td style=\"padding:0 20px 12px 20px;\">"
            f"<p style=\"color:#FFFFFF; font-size:15px; font-weight:600; margin:0 0 12px 0;\">{advice_headline}</p>"
            f"<p style=\"color:#8888AA; font-size:13px; line-height:1.7; margin:0 0 16px 0;\">{advice_context}</p>"
            "<div style=\"background:#0D0D2B; border-radius:4px; padding:12px 16px; margin-bottom:12px;\">"
            "<p style=\"color:#5C6BFF; font-size:10px; letter-spacing:1px; margin:0 0 8px 0;\">WHAT TO DO</p>"
            f"{playbook_html}"
            "</div>"
            f"<p style=\"color:#555570; font-size:12px; font-style:italic; margin:0 0 8px 0;\">{advice_benchmark}</p>"
            "<div style=\"background:#2B1515; border-radius:4px; padding:10px 14px;\">"
            f"<p style=\"color:#FF6B6B; font-size:12px; line-height:1.6; margin:0;\">⚠ {advice_urgency}</p>"
            "</div>"
            "</td></tr>"
            f"{target_section}"
            "</table>"
            "</td>"
            "</tr>"
        )

    actions_html = "".join(action_blocks) or (
        "<tr><td style=\"color:#8888AA; padding:8px 0 0 0;\">No actions detected for today.</td></tr>"
    )

    safe_unsubscribe_url = escape(str(unsubscribe_url or "#"), quote=True)
    html = (
        "<!doctype html>"
        "<html><head>"
        "<meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
        "<title>Perspicor Daily Report</title>"
        "</head>"
        "<body style=\"margin:0; padding:0; background-color:#08080F; font-family:system-ui, -apple-system, Arial, sans-serif;\">"
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\" style=\"background-color:#08080F;\">"
        "<tr><td align=\"center\" style=\"padding:20px 10px;\">"
        "<table role=\"presentation\" width=\"620\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\" "
        "style=\"width:100%; max-width:620px; background-color:#08080F;\">"
        "<tr><td style=\"padding:0 0 14px 0;\">"
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\">"
        "<tr>"
        f"<td style=\"color:#FFFFFF; font-size:16px; font-weight:700; letter-spacing:0.2px;\">{store_name}</td>"
        f"<td align=\"right\" style=\"color:#8888AA; font-size:13px;\">{date_text}</td>"
        "</tr>"
        "<tr><td colspan=\"2\" style=\"padding-top:8px;\"><div style=\"height:1px; background-color:#5C6BFF; line-height:1px;\">&nbsp;</div></td></tr>"
        "<tr><td colspan=\"2\" style=\"padding-top:10px;\">"
        f"<span style=\"display:inline-block; padding:5px 12px; border-radius:999px; background-color:{status_bg}; color:{status_fg}; border:1px solid {status_fg}; font-size:11px; font-weight:700; letter-spacing:0.4px;\">{status_label}</span>"
        "</td></tr>"
        "</table>"
        "</td></tr>"
        "<tr><td style=\"padding:14px 0 12px 0;\">"
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\" style=\"background-color:#12121E; border:1px solid #1E1E35; border-radius:8px;\">"
        "<tr><td style=\"padding:24px 24px 8px 24px; color:#8888AA; font-size:11px; text-transform:uppercase; letter-spacing:2px;\">Today's Opportunity</td></tr>"
        "<tr><td style=\"padding:0 24px 8px 24px;\">"
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\">"
        "<tr>"
        "<td width=\"33.33%\" valign=\"top\" style=\"padding:0 10px 0 0;\">"
        "<div style=\"color:#8888AA; font-size:11px; text-transform:uppercase; letter-spacing:1px; margin-bottom:4px;\">Daily Impact</div>"
        f"<div style=\"color:#5C6BFF; font-size:28px; line-height:1.2; font-weight:800;\">{escape(daily_impact)}</div>"
        "</td>"
        "<td width=\"33.33%\" valign=\"top\" style=\"padding:0 10px;\">"
        "<div style=\"color:#8888AA; font-size:11px; text-transform:uppercase; letter-spacing:1px; margin-bottom:4px;\">Total Value</div>"
        f"<div style=\"color:#5C6BFF; font-size:28px; line-height:1.2; font-weight:800;\">{escape(total_value)}</div>"
        "</td>"
        "<td width=\"33.33%\" valign=\"top\" style=\"padding:0 0 0 10px;\">"
        "<div style=\"color:#8888AA; font-size:11px; text-transform:uppercase; letter-spacing:1px; margin-bottom:4px;\">7-Day Projection</div>"
        f"<div style=\"color:#5C6BFF; font-size:28px; line-height:1.2; font-weight:800;\">{escape(projection)}</div>"
        "</td>"
        "</tr>"
        "</table>"
        "</td></tr>"
        f"<tr><td style=\"padding:16px 24px 24px 24px; color:#555570; font-size:12px; font-style:italic;\">Root cause: {root_cause}</td></tr>"
        "</table>"
        "</td></tr>"
        "<tr><td style=\"padding:0 0 12px 0;\">"
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\" style=\"border:1px solid #1E1E35; border-radius:8px;\">"
        "<tr>"
        "<td width=\"50%\" valign=\"top\" style=\"padding:0; background-color:#0D0D2B;\">"
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\">"
        "<tr><td style=\"padding:14px 16px 6px 16px; color:#5C6BFF; font-size:11px; font-weight:700; letter-spacing:2px; text-transform:uppercase;\">EXECUTE</td></tr>"
        f"<tr><td style=\"padding:0 16px 6px 16px; color:#5C6BFF; font-size:32px; font-weight:800;\">{escape(execute_value)}</td></tr>"
        "<tr><td style=\"padding:0 16px 14px 16px; color:#7B88FF; font-size:11px;\">recovered if you act today</td></tr>"
        "</table>"
        "</td>"
        "<td width=\"50%\" valign=\"top\" style=\"padding:0; background-color:#2B1515;\">"
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\">"
        "<tr><td style=\"padding:14px 16px 6px 16px; color:#FF6B6B; font-size:11px; font-weight:700; letter-spacing:2px; text-transform:uppercase;\">IGNORE</td></tr>"
        f"<tr><td style=\"padding:0 16px 6px 16px; color:#FF6B6B; font-size:32px; font-weight:800;\">{escape(ignore_loss)}</td></tr>"
        "<tr><td style=\"padding:0 16px 14px 16px; color:#FF6B6B; font-size:11px;\">projected 7-day loss</td></tr>"
        "</table>"
        "</td>"
        "</tr>"
        "<tr><td colspan=\"2\" style=\"padding:10px 12px; background-color:#151520; text-align:center;\">"
        f"<div style=\"color:#5C6BFF; font-size:14px; font-weight:700;\">DELTA: {escape(delta)}</div>"
        "<div style=\"color:#555570; font-size:11px; margin-top:3px;\">You leave this on the table every 7 days you wait</div>"
        "</td></tr>"
        "</table>"
        "</td></tr>"
        f"{actions_html}"
        "<tr><td style=\"padding:8px 0 0 0; border-top:1px solid #1E1E35;\">"
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\">"
        "<tr><td align=\"center\" style=\"padding:12px 0 4px 0; color:#333355; font-size:11px;\">Perspicor Daily Report - Confidential</td></tr>"
        "<tr><td align=\"center\" style=\"padding:0 0 10px 0; font-size:11px;\">"
        f"<a href=\"{safe_unsubscribe_url}\" style=\"color:#333355; text-decoration:underline;\">Unsubscribe</a>"
        "</td></tr>"
        "</table>"
        "</td></tr>"
        "</table>"
        "</td></tr>"
        "<tr><td align=\"center\" style=\"padding:0; background-color:#F6F7FA;\">"
        "<table role=\"presentation\" width=\"620\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\" "
        "style=\"width:100%; max-width:620px; background-color:#F6F7FA;\">"
        "<tr><td align=\"center\" style=\"padding:22px 20px 20px 20px;\">"
        f"{footer_logo_html}"
        "<div style=\"margin-top:10px; color:#141423; font-size:13px; font-weight:600; letter-spacing:0.2px;\">perspicor.com</div>"
        "<div style=\"margin-top:6px; color:#9AA0AD; font-size:11px; line-height:1.5;\">Unmatched perspicacity for your shopify store</div>"
        "</td></tr>"
        "</table>"
        "</td></tr>"
        "</table>"
        "</body></html>"
    )
    return _minify_email_html(html)
