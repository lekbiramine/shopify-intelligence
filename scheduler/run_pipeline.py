from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
from collections import defaultdict

import psycopg2
from psycopg2.extras import RealDictCursor

from config.logging_config import get_logger
from config import constants as app_constants
from config import settings
from db.queries import (
    count_store_sync_stats,
    create_report_record,
    get_store_contact_email_by_id,
    get_store_display_name_by_id,
    update_store_display_name_by_id,
    deactivate_likely_test_stores,
    list_manual_reportable_stores,
    update_store_auth_tokens,
)
from etl.extract import (
    deduplicate_customers_from_orders,
    fetch_products,
    fetch_orders,
    fetch_inventory_levels,
)
from etl.transform import (
    transform_products,
    transform_customers,
    transform_orders,
    transform_inventory,
)
from etl.load import (
    attach_store_id,
    load_products,
    load_customers,
    load_orders,
    load_inventory,
)
from analytics.summary import build_summary
from analytics.insights.insight_low_repeat_purchase_rate import run_insight as run_low_repeat_purchase_rate_insight
from analytics.insights.insight_high_value_customer_at_risk import run_insight as run_high_value_customer_at_risk_insight
from analytics.insights.insight_abandoned_checkout_spike import run_insight as run_abandoned_checkout_spike_insight
from analytics.insights.insight_low_margin_products import run_insight as run_low_margin_products_insight
from reporting.email_sender import send_store_report_email
from reporting.pdf_report_v2 import build_structured_actions
from tasks.engine import (
    auto_verify_tasks_from_summary,
    build_report_task_sections,
    collect_due_reminders,
    evaluate_completed_task_impacts,
    sync_tasks_from_summary,
)
from utils.decorators import log_execution
from utils.shopify_auth import (
    fetch_access_scopes,
    fetch_shop_display_name,
    migrate_non_expiring_offline_token,
    refresh_access_token,
    validate_access_token,
    validate_read_only_scopes,
)

logger = get_logger(__name__)

REGISTERED_INSIGHT_ACTIONS = [
    "dead_inventory",
    "high_return_rate",
    "churned_customers",
    "low_repeat_purchase_rate",
    "high_value_customer_at_risk",
    "abandoned_checkout_spike",
    "low_margin_products",
    "duplicate_orders",
    "revenue_concentration",
    "abnormal_discount",
]

REGISTERED_INSIGHT_ACTION_TYPES = frozenset(REGISTERED_INSIGHT_ACTIONS)

REGISTERED_INSIGHT_RUNNERS = (
    run_low_repeat_purchase_rate_insight,
    run_high_value_customer_at_risk_insight,
    run_abandoned_checkout_spike_insight,
    run_low_margin_products_insight,
)


def _log_insight_detection_line(slug: str, detected: bool) -> None:
    print(f"[insight] {slug} -> {'detected' if detected else 'not triggered'}", flush=True)


def _log_all_registered_insight_signals(store_id: int) -> None:
    """Diagnostic print after each registered insight runner (legacy + new SQL signals)."""
    from analytics.insights import insight_churned_customers, insight_dead_inventory, insight_high_return_rate

    result = insight_churned_customers(store_id)
    _log_insight_detection_line("churned_customers", bool(result))

    high_rr = insight_high_return_rate(store_id)
    _log_insight_detection_line("high_return_rate", len(high_rr) > 0)

    dead_inv = insight_dead_inventory(store_id)
    _log_insight_detection_line("dead_inventory", len(dead_inv) > 0)

    for slug, runner in (
        ("low_repeat_purchase_rate", run_low_repeat_purchase_rate_insight),
        ("high_value_customer_at_risk", run_high_value_customer_at_risk_insight),
        ("abandoned_checkout_spike", run_abandoned_checkout_spike_insight),
        ("low_margin_products", run_low_margin_products_insight),
    ):
        with psycopg2.connect(
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            dbname=settings.DB_NAME,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
        ) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                raw = runner(cursor, store_id=store_id)
        detected = bool(raw.get("detected")) if isinstance(raw, dict) else False
        _log_insight_detection_line(slug, detected)


def _ensure_store_access_token(
    *,
    shop_domain: str,
    access_token: str,
    refresh_token: str | None = None,
    access_token_expires_at=None,
) -> str:
    """
    Returns a usable access token, refreshing it when needed.
    """
    token = (access_token or "").strip()
    if not token:
        raise RuntimeError(f"Missing access token for {shop_domain}")

    # Refresh proactively if token is near expiry.
    should_refresh = False
    if access_token_expires_at:
        try:
            if datetime.now(timezone.utc) + timedelta(minutes=2) >= access_token_expires_at:
                should_refresh = True
        except Exception:
            logger.warning("Invalid access_token_expires_at for %s; continuing with current token", shop_domain)

    if should_refresh:
        if not (refresh_token or "").strip():
            raise RuntimeError(f"Access token for {shop_domain} is expiring and no refresh token is stored.")
        refreshed = refresh_access_token(shop_domain, refresh_token)
        token = refreshed["access_token"]
        update_store_auth_tokens(
            shop_domain,
            access_token=token,
            refresh_token=refreshed.get("refresh_token"),
            access_token_expires_at=refreshed.get("access_token_expires_at"),
        )
        logger.info("Refreshed access token for %s", shop_domain)
        return token

    token_ok, _ = validate_access_token(shop_domain, token)
    if token_ok:
        return token

    # If current token is invalid and we have a refresh token, rotate and retry.
    if (refresh_token or "").strip():
        refreshed = refresh_access_token(shop_domain, refresh_token)
        token = refreshed["access_token"]
        update_store_auth_tokens(
            shop_domain,
            access_token=token,
            refresh_token=refreshed.get("refresh_token"),
            access_token_expires_at=refreshed.get("access_token_expires_at"),
        )
        logger.info("Rotated invalid access token for %s", shop_domain)
        return token

    # Last attempt: one-time Shopify migration from non-expiring -> expiring offline token.
    migrated = migrate_non_expiring_offline_token(shop_domain, token)
    token = migrated["access_token"]
    update_store_auth_tokens(
        shop_domain,
        access_token=token,
        refresh_token=migrated.get("refresh_token"),
        access_token_expires_at=migrated.get("access_token_expires_at"),
    )
    logger.info("Migrated non-expiring offline token for %s", shop_domain)
    return token


@log_execution
def run_etl_for_store(
    *,
    store_id: int,
    shop_domain: str,
    access_token: str,
    refresh_token: str | None = None,
    access_token_expires_at=None,
) -> None:
    logger.info("Starting ETL pipeline...")
    access_token = _ensure_store_access_token(
        shop_domain=shop_domain,
        access_token=access_token,
        refresh_token=refresh_token,
        access_token_expires_at=access_token_expires_at,
    )
    token_ok, token_detail = validate_access_token(shop_domain, access_token)
    if not token_ok:
        raise RuntimeError(f"Token validation failed for {shop_domain}: {token_detail}")

    # Best-effort: persist the merchant-facing store name for nicer emails.
    try:
        shop_name = fetch_shop_display_name(shop_domain, access_token)
        if shop_name:
            update_store_display_name_by_id(store_id=store_id, display_name=shop_name)
    except Exception:
        logger.debug("Unable to fetch/persist display_name for %s", shop_domain)
    scopes = fetch_access_scopes(shop_domain, access_token)
    logger.info("Granted scopes for %s: %s", shop_domain, ",".join(scopes))
    scopes_ok, scopes_detail = validate_read_only_scopes(scopes)
    if not scopes_ok:
        raise RuntimeError(f"Scope validation failed for {shop_domain}: {scopes_detail}")
    logger.info(
        "Scope check passed for %s (read_customers=%s, read_orders=%s)",
        shop_domain,
        "read_customers" in set(scopes),
        "read_orders" in set(scopes),
    )

    # Extract (customers are derived from order payloads — no standalone Customers API)
    raw_products = fetch_products(shop_domain=shop_domain, access_token=access_token)
    raw_orders = fetch_orders(shop_domain=shop_domain, access_token=access_token)
    raw_customers = deduplicate_customers_from_orders(raw_orders)

    # Transform
    products, variants = transform_products(raw_products)
    customers = transform_customers(raw_customers)
    orders, order_items = transform_orders(raw_orders)

    # Extract inventory item IDs from variants
    inventory_item_ids = [
        v["id"] for v in variants if v.get("id")
    ]
    raw_inventory = fetch_inventory_levels(inventory_item_ids, shop_domain=shop_domain, access_token=access_token)
    inventory = transform_inventory(raw_inventory)

    # Load
    load_products(attach_store_id(products, store_id), attach_store_id(variants, store_id))
    load_customers(attach_store_id(customers, store_id))
    load_orders(attach_store_id(orders, store_id), attach_store_id(order_items, store_id))
    load_inventory(attach_store_id(inventory, store_id))

    sync_stats = count_store_sync_stats(store_id)
    logger.info(
        "ETL pipeline completed for store_id=%s: products=%s variants=%s orders=%s",
        store_id,
        sync_stats["products"],
        sync_stats["variants"],
        sync_stats["orders"],
    )
    if sync_stats["products"] == 0:
        raise RuntimeError(
            f"ETL synced zero products for {shop_domain}. "
            "Verify the app has read_products scope and the store has active products."
        )


def _assert_store_report_delivery_scope(*, store_id: int, report_path: str, recipient_email: str) -> None:
    expected = get_store_contact_email_by_id(store_id)
    if not expected:
        raise RuntimeError(f"No contact_email configured for store_id={store_id}")
    if recipient_email.strip().lower() != expected.strip().lower():
        raise RuntimeError(
            f"Recipient email mismatch for store_id={store_id}: expected {expected}, got {recipient_email}"
        )
    normalized = str(Path(report_path)).replace("\\", "/")
    if f"/reports/{store_id}/" not in f"/{normalized}":
        raise RuntimeError(f"Report path is not store-scoped: {report_path}")


def _problem_for_routing(summary: dict, routing_slug: str) -> str:
    slug = routing_slug.strip().lower()
    for ins in summary.get("insights") or []:
        if str(ins.get("routing_type") or "").strip().lower() == slug:
            return str(ins.get("problem") or ins.get("impact") or "")
    return ""


def _dead_inventory_target_rows_from_summary(summary: dict, *, limit: int = 8) -> list[dict]:
    rows: list[dict] = []
    products = sorted(
        list((summary.get("anomalies") or {}).get("no_sales_products") or []),
        key=lambda p: float(p.get("est_on_hand_value") or 0),
        reverse=True,
    )[:limit]
    for p in products:
        sku = str(p.get("primary_sku") or "").strip() or "N/A"
        rows.append(
            {
                "name": str(p.get("product_title") or "Unknown product"),
                "sku": sku,
                "inventory": int(p.get("total_available") or 0),
                "sales_last_90d": 0,
            }
        )
    return rows


def _build_email_report_data(*, store_id: int, report_payload: dict, summary: dict) -> dict:
    contract = report_payload.get("report_contract") or {}
    metadata = contract.get("metadata") or {}
    financials = contract.get("financials") or {}
    decision = contract.get("decision_block") or {}
    contract_actions = list(contract.get("actions") or [])

    enriched_actions = list(report_payload.get("actions") or [])
    enriched_by_id = {str(a.get("id") or ""): a for a in enriched_actions if str(a.get("id") or "").strip()}
    fallback_pool = build_structured_actions(
        summary, max_actions=max(48, app_constants.REPORT_EMAIL_MAX_ACTIONS * 12)
    )
    fallback_by_route: dict[str, list[dict]] = defaultdict(list)
    for row in fallback_pool:
        rt = str(row.get("email_routing_type") or "").strip().lower()
        if rt:
            fallback_by_route[rt].append(row)
    fallback_route_pos: defaultdict[str, int] = defaultdict(int)
    revenue_trend = (summary.get("revenue") or {}).get("trend") or {}
    orders_7d = float(revenue_trend.get("current_7d_orders") or 0.0)
    revenue_7d = float(revenue_trend.get("current_7d_net_revenue") or 0.0)
    store_aov = (revenue_7d / orders_7d) if orders_7d > 0 else 0.0

    def _infer_action_type(*, diagnosis: str, intervention: str, enriched: dict) -> str:
        route = str((enriched or {}).get("email_routing_type") or "").strip().lower()
        if route and route in REGISTERED_INSIGHT_ACTION_TYPES:
            return route

        text = f"{diagnosis} {intervention}".lower()

        def _looks_like_duplicate(txt: str) -> bool:
            if "duplicate" not in txt:
                return False
            if "order rate" in txt or "repeat rate" in txt:
                return False
            return "order" in txt or "orders" in txt or "charge" in txt

        if _looks_like_duplicate(text):
            return "duplicate_orders"
        if ("one-time buyers" in text) or ("customers reorder" in text and "%" in diagnosis.lower()):
            return "low_repeat_purchase_rate"
        if "return rate" in text or "returned unit" in text or "% return" in text:
            return "high_return_rate"
        if ("dead inventory" in text) or ("zero sales" in text and "inventory" in text):
            return "dead_inventory"
        if "vip" in text and ("risk" in text or "quiet" in text):
            return "high_value_customer_at_risk"
        if "loyal revenue" in text and "top 2" in text:
            return "revenue_concentration"
        if ("abandon" in text and "checkout" in text) or ("abandoned" in text and "cart" in text):
            return "abandoned_checkout_spike"
        if "discount" in text and "order" in text:
            return "abnormal_discount"
        if "churn" in text or "inactive for 90" in text or "win-back" in text:
            return "churned_customers"
        if ("repeat" in text and "purchase" in text) or "repeat rate" in text:
            return "low_repeat_purchase_rate"
        if "margin" in text and ("profit" in text or "price increase" in text):
            return "low_margin_products"

        coarse = str((enriched or {}).get("type") or "").strip().lower()
        if coarse == "returns":
            return "high_return_rate"
        if coarse == "inventory":
            return "dead_inventory"

        return "low_margin_products"

    def _parse_target_row(raw_target: object) -> dict | None:
        if isinstance(raw_target, dict):
            ds_raw = raw_target.get("days_since_order")
            dsi = None
            if ds_raw is not None:
                try:
                    dsi = int(round(float(ds_raw)))
                except (TypeError, ValueError):
                    dsi = None
            inv_raw = raw_target.get("inventory")
            inv_coerced = None
            if inv_raw is not None:
                try:
                    inv_coerced = int(inv_raw)
                except (TypeError, ValueError):
                    inv_coerced = None

            def _coerce_float(v: object) -> float | None:
                if v is None:
                    return None
                try:
                    return float(v)
                except (TypeError, ValueError):
                    return None

            def _coerce_int(v: object) -> int | None:
                if v is None:
                    return None
                try:
                    return int(v)
                except (TypeError, ValueError):
                    try:
                        return int(round(float(v)))
                    except (TypeError, ValueError):
                        return None

            return {
                "name": str(raw_target.get("name") or "").strip(),
                "sku": str(raw_target.get("sku") or "N/A").strip() or "N/A",
                "inventory": inv_coerced,
                "sales_last_90d": raw_target.get("sales_last_90d") or raw_target.get("units_sold"),
                "return_rate": raw_target.get("return_rate"),
                "returned_units": raw_target.get("returned_units"),
                "email": raw_target.get("email"),
                "ltv": _coerce_float(raw_target.get("ltv")),
                "total_spent": _coerce_float(raw_target.get("total_spent")),
                "orders_count": _coerce_int(raw_target.get("orders_count")),
                "days_since_order": dsi,
                "price": _coerce_float(raw_target.get("price")),
                "units_sold": _coerce_int(raw_target.get("units_sold")),
            }
        text = str(raw_target or "").strip()
        if not text:
            return None
        parts = [p.strip() for p in text.split("—")]
        name = parts[0] if parts else text
        sku = "N/A"
        inventory = None
        sales_last_90d = None
        return_rate = None
        returned_units = None

        sku_match = re.search(r"SKU\s*[:#-]?\s*([A-Za-z0-9_\-]+)", text, flags=re.IGNORECASE)
        if sku_match:
            sku = sku_match.group(1).strip()
        elif name:
            # Some return-rate alerts include product identifier only (no explicit SKU token).
            sku = name

        inv_match = re.search(
            r"(?:inventory|on\s*hand)\s*[:=]?\s*(\d+)", text, flags=re.IGNORECASE
        )
        if inv_match:
            inventory = int(inv_match.group(1))

        sales_match = re.search(
            r"90d\s*sales\s*[:=]?\s*(\d+)|sales\s*[:=]?\s*(\d+)\s*(?:in\s*last\s*90d|90d)?",
            text,
            flags=re.IGNORECASE,
        )
        if sales_match:
            g1, g2 = sales_match.group(1), sales_match.group(2)
            g_raw = g1 if g1 is not None else g2
            if g_raw:
                sales_last_90d = int(g_raw)


        return_match = re.search(r"(\d+(?:\.\d+)?)\s*%\s*return", text, flags=re.IGNORECASE)
        if return_match:
            return_rate = float(return_match.group(1))
        returned_match = re.search(r"(\d+)\s+returned\s+unit", text, flags=re.IGNORECASE)
        if returned_match:
            returned_units = int(returned_match.group(1))
        ltv_match = re.search(r"ltv\s*[:=]?\s*\$?\s*([\d,]+(?:\.\d+)?)", text, flags=re.IGNORECASE)
        days_since_match = re.search(
            r"(?:(\d+)\s*d(?:ays?)?\s+since|(\d+)\s+days\s+since\s+last\s+order)",
            text,
            flags=re.IGNORECASE,
        )
        email_match = re.search(r"([a-zA-Z0-9][^@\s]{0,10}\*{0,3}@[^\s]+)", text)
        price_match = re.search(
            r"price\s*[:=]?\s*\$?\s*([\d,]+(?:\.\d+)?)", text, flags=re.IGNORECASE
        )
        units_sold_match = re.search(r"units?\s*sold\s*[:=]?\s*(\d+)", text, flags=re.IGNORECASE)
        units_90d_match = re.search(r"units sold 90d\s*(\d+)", text, flags=re.IGNORECASE)
        spend_conc_match = re.search(r"SPEND:\s*\$?\s*([\d,]+(?:\.\d+)?)", text, flags=re.IGNORECASE)
        if not spend_conc_match:
            spend_conc_match = re.search(
                r"\bspend\s+\$?\s*([\d,]+(?:\.\d+)?)", text, flags=re.IGNORECASE
            )
        orders_conc_match = re.search(r"ORDERS:\s*(\d+)", text, flags=re.IGNORECASE)
        if not orders_conc_match:
            orders_conc_match = re.search(r"\b(\d+)\s+orders\b", text, flags=re.IGNORECASE)

        def _strip_money(m: re.Match[str] | None) -> float | None:
            if not m:
                return None
            return float(m.group(1).replace(",", ""))

        us_raw = units_sold_match.group(1) if units_sold_match else None
        if us_raw is None and units_90d_match:
            us_raw = units_90d_match.group(1)
        ltv_val = _strip_money(ltv_match)
        price_val = _strip_money(price_match)
        spend_val = _strip_money(spend_conc_match)
        orders_conc = int(orders_conc_match.group(1)) if orders_conc_match else None

        return {
            "name": name,
            "sku": sku,
            "inventory": inventory,
            "sales_last_90d": sales_last_90d,
            "return_rate": return_rate,
            "returned_units": returned_units,
            "email": email_match.group(1).strip() if email_match else None,
            "ltv": ltv_val,
            "total_spent": spend_val,
            "orders_count": orders_conc,
            "days_since_order": (
                int(next(g for g in days_since_match.groups() if g is not None))
                if days_since_match
                else None
            ),
            "price": price_val,
            "units_sold": int(us_raw) if us_raw is not None else None,
        }

    def _target_rows_from_insight_routing(route_key: str) -> list[dict]:
        rows: list[dict] = []
        rk = str(route_key or "").strip().lower()
        for ins in summary.get("insights") or []:
            if str(ins.get("routing_type") or "").strip().lower() != rk:
                continue
            for line in ins.get("exact_items") or []:
                parsed = _parse_target_row(line)
                if parsed:
                    rows.append(parsed)
            break
        return rows

    actions: list[dict] = []
    for idx, action in enumerate(contract_actions, start=1):
        action_id = str(action.get("id") or "")
        enriched = enriched_by_id.get(action_id, {})
        slug = str(enriched.get("email_routing_type") or "").strip().lower()
        flist = fallback_by_route.get(slug, []) if slug else []
        fp = fallback_route_pos[slug]
        fallback_row: dict = flist[fp] if slug and fp < len(flist) else {}
        if slug and fp < len(flist):
            fallback_route_pos[slug] = fp + 1

        expected = action.get("expected_outcome") or {}
        diagnosis = str(
            action.get("diagnosis") or fallback_row.get("context") or "Issue is reducing profitability."
        )
        intervention = str(
            action.get("intervention")
            or fallback_row.get("execute_command")
            or "Execute highest-priority action now."
        )

        action_type = _infer_action_type(diagnosis=diagnosis, intervention=intervention, enriched=enriched)

        raw_targets = list(
            action.get("targets") or enriched.get("targets") or fallback_row.get("targets") or []
        )
        if action_type == "dead_inventory":
            target_rows = _dead_inventory_target_rows_from_summary(summary)
        elif action_type == "low_margin_products":
            target_rows = _target_rows_from_insight_routing("low_margin_products")
            if not target_rows:
                for target in raw_targets:
                    parsed = _parse_target_row(target)
                    if parsed:
                        target_rows.append(parsed)
        elif action_type == "revenue_concentration":
            target_rows = _target_rows_from_insight_routing("revenue_concentration")
            if not target_rows:
                for target in raw_targets:
                    parsed = _parse_target_row(target)
                    if parsed:
                        target_rows.append(parsed)
        else:
            target_rows = []
            for target in raw_targets:
                parsed = _parse_target_row(target)
                if parsed:
                    target_rows.append(parsed)
        risk_amount = float(expected.get("risk_if_ignored") or 0.0)
        weekly_value = float(expected.get("weekly_value") or fallback_row.get("value") or 0.0)

        metrics: dict = {"store_aov": store_aov}
        if action_type == "dead_inventory":
            sku_count = len(target_rows)
            total_units = sum(int(row.get("inventory") or 0) for row in target_rows)
            estimated_value = weekly_value
            metrics.update(
                {
                    "sku_count": sku_count,
                    "total_units": total_units,
                    "days_stale": 90,
                    "estimated_value": estimated_value,
                }
            )
        elif action_type == "high_return_rate":
            first = target_rows[0] if target_rows else {}
            rr_pct = float(first.get("return_rate") or 0.0)
            returned_units = int(first.get("returned_units") or 0)
            pname = str(first.get("name") or "").strip()
            if not pname or pname == "N/A":
                prob_hr = diagnosis or _problem_for_routing(summary, "high_return_rate")
                qm = re.search(r'"([^"]+)"\s+has\s+a\s+([\d.]+)%', prob_hr)
                if qm:
                    pname = qm.group(1).strip()
                    if rr_pct <= 0:
                        rr_pct = float(qm.group(2))
            if not pname:
                pname = "This product"
            metrics.update(
                {
                    "product_name": pname,
                    "return_rate": rr_pct / 100.0 if rr_pct > 1 else rr_pct,
                    "returned_units": returned_units,
                    "revenue_lost": weekly_value,
                    "avg_return_rate_healthy": 0.05,
                }
            )
        elif action_type == "low_repeat_purchase_rate":
            prob_text = diagnosis or _problem_for_routing(summary, "low_repeat_purchase_rate")
            one_time_buyers = 0
            m_ot = re.search(r"(\d+)\s+one-time buyers", prob_text, re.I)
            if m_ot:
                one_time_buyers = max(int(m_ot.group(1)), 0)
            elif target_rows:
                one_time_buyers = len(target_rows)
            pct_m = re.search(r"(?:only\s+)?([\d.]+)\s*%\s+of\s+customers\s+reorder", prob_text, re.I)
            repeat_rate = float(pct_m.group(1)) / 100.0 if pct_m else 0.0
            revenue_if_10pct = weekly_value if weekly_value > 0 else (max(one_time_buyers, 1) * store_aov * 0.10)
            denom = max(1.0 - repeat_rate, 0.05) if repeat_rate > 0 else 1.0
            total_customers_est = (
                max(int(round(one_time_buyers / denom)), one_time_buyers) if one_time_buyers > 0 else max(one_time_buyers, 1)
            )
            if repeat_rate <= 0.0 and one_time_buyers > 0 and total_customers_est > 0:
                repeat_rate = max(min(1.0 - (one_time_buyers / total_customers_est), 1.0), 0.0)
            if total_customers_est <= 0:
                total_customers_est = max(one_time_buyers, 1)
            metrics.update(
                {
                    "repeat_rate": max(min(repeat_rate, 1.0), 0.0),
                    "total_customers": int(total_customers_est),
                    "one_time_buyers": max(int(one_time_buyers), 0),
                    "store_aov": store_aov,
                    "revenue_if_10pct_improvement": float(revenue_if_10pct),
                }
            )
        elif action_type == "duplicate_orders":
            m_cust = re.search(r"customer\s+(\d+)", diagnosis, re.I)
            m_ord = re.search(r"(\d+)\s+duplicate\s+orders", diagnosis, re.I)
            dup_n = int(m_ord.group(1)) if m_ord else 2
            customer_id_disp = str(m_cust.group(1)).strip() if m_cust else ""
            exposure = weekly_value if weekly_value > 0 else 0.0
            metrics.update(
                {
                    "customer_id_display": customer_id_disp,
                    "duplicate_order_entries": dup_n,
                    "duplicate_charge_exposure": float(exposure),
                    "store_aov": store_aov,
                }
            )
        elif action_type == "revenue_concentration":
            loyal = list((summary.get("customers") or {}).get("loyal") or [])
            total_loyal = sum(float(c.get("total_spent") or 0) for c in loyal)
            top2 = loyal[:2]
            top2_rev = sum(float(c.get("total_spent") or 0) for c in top2)
            pct = (top2_rev / total_loyal * 100.0) if total_loyal > 0 else 0.0
            metrics.update(
                {
                    "concentration_pct": round(pct, 1),
                    "top_two_revenue_share": round(top2_rev, 2),
                    "loyal_revenue_pool": round(total_loyal, 2),
                    "store_aov": store_aov,
                }
            )
        elif action_type == "abnormal_discount":
            m_oid = re.search(r"order\s+(\d+)", diagnosis, re.I)
            m_pct = re.search(r"([\d.]+)%\s*discount", diagnosis, re.I)
            metrics.update(
                {
                    "order_id_hint": str(m_oid.group(1)) if m_oid else "",
                    "discount_pct_hint": float(m_pct.group(1)) if m_pct else 0.0,
                    "estimated_leak_usd": float(weekly_value),
                    "store_aov": store_aov,
                }
            )
        elif action_type == "churned_customers":
            churned = list((summary.get("customers") or {}).get("churned") or [])
            churned_count = len(churned)
            potential_recovery = sum(
                float(c.get("total_spent") or 0) / max(int(c.get("orders_count") or 1), 1) for c in churned
            )
            ds_vals: list[float] = []
            for c in churned:
                d = c.get("days_since_last_order")
                if d is not None:
                    try:
                        ds_vals.append(float(d))
                    except (TypeError, ValueError):
                        continue
            avg_days_since = round(sum(ds_vals) / len(ds_vals), 1) if ds_vals else 0.0
            metrics.update(
                {
                    "churned_count": int(churned_count),
                    "potential_recovery": float(potential_recovery),
                    "avg_days_since_order": float(avg_days_since),
                    "top_churned_product": "your top categories",
                    "store_aov": store_aov,
                }
            )
        elif action_type == "high_value_customer_at_risk":
            customer_count = len(target_rows)
            if customer_count <= 0:
                prob_v = diagnosis or _problem_for_routing(summary, "high_value_customer_at_risk")
                mh = re.search(r"(\d+)\s+high-value customers", prob_v, re.I)
                if mh:
                    customer_count = max(int(mh.group(1)), 0)
            avg_ltv = (
                sum(float(row.get("ltv") or 0.0) for row in target_rows) / customer_count
                if customer_count > 0
                else 0.0
            )
            avg_days = (
                sum(float(row.get("days_since_order") or 0.0) for row in target_rows) / customer_count
                if customer_count > 0
                else 0.0
            )
            total_ltv_at_risk = float(weekly_value if weekly_value > 0 else (customer_count * avg_ltv))
            metrics.update(
                {
                    "customer_count": int(customer_count),
                    "avg_ltv": float(avg_ltv),
                    "days_since_last_order": float(avg_days),
                    "total_ltv_at_risk": float(total_ltv_at_risk),
                    "store_aov": store_aov,
                }
            )
        elif action_type == "abandoned_checkout_spike":
            abandoned_count = len(target_rows)
            if abandoned_count <= 0:
                prob_a = diagnosis or _problem_for_routing(summary, "abandoned_checkout_spike")
                ma = re.search(r"(\d+)\s+checkouts\s+abandoned", prob_a, re.I)
                if ma:
                    abandoned_count = max(int(ma.group(1)), 1)
                else:
                    abandoned_count = max(abandoned_count, 1)
            abandoned_count = max(abandoned_count, 1)
            potential_revenue = float(weekly_value if weekly_value > 0 else (abandoned_count * store_aov))
            abandonment_rate = 0.75 if abandoned_count > 0 else 0.0
            prev_rate = max(abandonment_rate - 0.08, 0.0)
            metrics.update(
                {
                    "abandoned_count": int(abandoned_count),
                    "abandonment_rate": float(abandonment_rate),
                    "potential_revenue": float(potential_revenue),
                    "store_aov": store_aov,
                    "prev_week_abandonment_rate": float(prev_rate),
                }
            )
        elif action_type == "low_margin_products":
            first = target_rows[0] if target_rows else {}
            units_sold = int(first.get("units_sold") or first.get("sales_last_90d") or 0)
            price_f = float(first.get("price") or 0.0)
            revenue_generated = price_f * float(units_sold) if units_sold and price_f else 0.0
            if revenue_generated <= 0.0:
                revenue_generated = float(
                    weekly_value if weekly_value > 0 else (max(units_sold, 1) * (price_f or store_aov))
                )
            estimated_margin = 0.60
            metrics.update(
                {
                    "product_name": str(first.get("name") or "This product"),
                    "units_sold": units_sold,
                    "estimated_margin": estimated_margin,
                    "revenue_generated": revenue_generated,
                    "profit_generated": revenue_generated * estimated_margin,
                    "store_avg_margin": 0.60,
                }
            )
        actions.append(
            {
                "number": int(action.get("priority") or idx),
                "type": "PRIMARY REVENUE LEAK" if idx == 1 else "SECONDARY OPTIMIZATION LEAK",
                "daily_impact": float(expected.get("daily_impact") or fallback_row.get("daily_loss") or 0.0),
                "problem": diagnosis,
                "fix": intervention,
                "impact_bullets": [
                    f"Recover ${weekly_value:,.2f} over 7 days",
                    f"Protect margin by acting today",
                ],
                "risk_bullets": [
                    f"Lose ${risk_amount:,.2f} in projected 7-day downside",
                    "Leak compounds each day action is delayed",
                ],
                "targets": target_rows,
                "state": str(action.get("state") or "PENDING"),
                "action_type": action_type,
                "metrics": metrics,
            }
        )

    generated_at = str(report_payload.get("generated_at") or "")
    date_label = generated_at.split("T", 1)[0] if "T" in generated_at else generated_at
    store_name = get_store_display_name_by_id(store_id) or f"Store {store_id}"

    return {
        "store_name": store_name,
        "date": date_label,
        "status": str(metadata.get("status") or "warning"),
        "daily_impact": float(financials.get("daily_impact") or 0.0),
        "total_value": float(financials.get("recoverable_7d") or 0.0),
        "seven_day_projection": float(financials.get("risk_7d") or 0.0),
        "root_cause": str(financials.get("root_cause") or report_payload.get("main_cause") or "OPERATIONAL REVENUE LEAK"),
        "execute_value": float(decision.get("execute_value") or 0.0),
        "ignore_loss": float(decision.get("ignore_value") or 0.0),
        "delta": float(decision.get("net_delta") or 0.0),
        "actions": actions,
    }


@log_execution
def run_reporting_for_store(*, store_id: int) -> tuple[str, str]:
    logger.info("[store_id=%s] Running report for shop_domain", store_id)
    logger.info("Starting reporting pipeline...", extra={"store_id": store_id})

    sync_stats = count_store_sync_stats(store_id)
    if sync_stats["products"] == 0:
        raise RuntimeError(
            f"Refusing to send report for store_id={store_id}: no products in database "
            "(run ETL first or re-connect the store)."
        )

    _log_all_registered_insight_signals(store_id)
    summary = build_summary(store_id)
    sync_tasks_from_summary(store_id, summary)
    auto_verify_tasks_from_summary(store_id, summary)
    evaluate_completed_task_impacts(store_id, summary)
    collect_due_reminders(store_id)
    _ = build_report_task_sections(store_id, summary)
    from api.store_intelligence_api import api_results

    report_payload = api_results(store_id)
    report_data = _build_email_report_data(store_id=store_id, report_payload=report_payload, summary=summary)
    report_path = str(Path("reports") / str(store_id) / "latest_results_report.json")
    recipient_email = get_store_contact_email_by_id(store_id) or ""
    _assert_store_report_delivery_scope(store_id=store_id, report_path=report_path, recipient_email=recipient_email)
    recipient = send_store_report_email(store_id=store_id, report_data=report_data)
    create_report_record(store_id=store_id, report_path=report_path, recipient_email=recipient)

    logger.info("Reporting pipeline completed.", extra={"store_id": store_id, "report_path": report_path, "recipient": recipient})
    return report_path, recipient


@log_execution
def run_etl() -> None:
    """
    Backwards compatible single-store ETL task driven by env vars.
    """
    settings.validate_shopify_pipeline_env()
    from db.queries import get_store_by_domain

    store = get_store_by_domain(settings.SHOPIFY_STORE_URL)
    if not store:
        raise RuntimeError("No store row found for SHOPIFY_STORE_URL; connect the store via onboarding first.")

    run_etl_for_store(
        store_id=store["id"],
        shop_domain=settings.SHOPIFY_STORE_URL,
        access_token=store.get("access_token") or settings.SHOPIFY_ACCESS_TOKEN,
        refresh_token=store.get("refresh_token"),
        access_token_expires_at=store.get("access_token_expires_at"),
    )


@log_execution
def run_reporting() -> None:
    """
    Backwards compatible single-store reporting task driven by env vars.
    """
    settings.validate_email_env()
    from db.queries import get_store_by_domain

    store = get_store_by_domain(settings.SHOPIFY_STORE_URL)
    if not store:
        raise RuntimeError("No store row found for SHOPIFY_STORE_URL; connect the store via onboarding first.")

    run_reporting_for_store(store_id=store["id"])


@log_execution
def run_pipeline() -> None:
    logger.info("=" * 50)
    logger.info("PIPELINE STARTED")
    logger.info("=" * 50)

    settings.validate_email_env()

    # Ensure the DB itself stays clean: legacy demo/test shops should not be scheduled.
    deactivated = deactivate_likely_test_stores()
    if deactivated:
        logger.warning(
            "Deactivated %s legacy test/demo stores that were still scheduled: %s",
            len(deactivated),
            ", ".join(f"{r.get('shop_domain')} (id={r.get('id')})" for r in deactivated),
        )

    stores = list_manual_reportable_stores()
    if not stores:
        logger.warning(
            "No reportable stores found. Ensure stores are active, have contact_email, "
            "and report_schedule_active=TRUE."
        )
        return

    logger.info("Running manual pipeline for %s stores.", len(stores))
    succeeded = 0
    failed = 0
    attempted = 0
    for store in stores:
        store_id = int(store["id"])
        shop_domain = str(store.get("shop_domain") or "").strip()
        attempted += 1
        try:
            run_etl_for_store(
                store_id=store_id,
                shop_domain=shop_domain,
                access_token=str(store.get("access_token") or "").strip(),
                refresh_token=(str(store.get("refresh_token") or "").strip() or None),
                access_token_expires_at=store.get("access_token_expires_at"),
            )
            run_reporting_for_store(store_id=store_id)
            logger.info("Manual pipeline completed for %s (store_id=%s)", shop_domain, store_id)
            succeeded += 1
        except Exception:
            logger.exception("Manual pipeline failed for %s (store_id=%s)", shop_domain, store_id)
            failed += 1

    logger.info("=" * 50)
    logger.info(
        "PIPELINE FINISHED | total=%s attempted=%s succeeded=%s failed=%s",
        len(stores),
        attempted,
        succeeded,
        failed,
    )
    logger.info("=" * 50)


if __name__ == "__main__":
    from config.logging_config import setup_logging

    setup_logging()
    run_pipeline()