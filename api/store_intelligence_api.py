from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from analytics.summary import build_summary
from reporting.pdf_report_v2 import build_structured_actions, create_report_pdf

app = FastAPI(title="Store Intelligence API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CompleteActionRequest(BaseModel):
    action_id: str


class BaselineMetrics(BaseModel):
    orders_7d: float
    revenue_7d: float


class ExpectedResult(BaseModel):
    metric: str
    baseline: float
    target: float
    time_window_days: int


class ActionResponse(BaseModel):
    id: str
    title: str
    value: float
    daily_loss: float
    priority_score: float
    priority_ratio: float
    priority_explanation: str
    rank: int
    context: str
    targets: list[str]
    execute_command: str
    goal: str
    measured_by: list[str]
    expected_result: ExpectedResult
    baseline_metrics: BaselineMetrics
    normalized_impact_weight: float


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _state_path(store_id: int) -> Path:
    out_dir = Path("reports") / str(store_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / "action_tracking.json"


def _reports_dir(store_id: int) -> Path:
    out_dir = Path("reports") / str(store_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _history_dir(store_id: int) -> Path:
    out_dir = _reports_dir(store_id) / "history"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _snapshot_path_for_date(store_id: int, snapshot_date: date) -> Path:
    return _history_dir(store_id) / f"{snapshot_date.isoformat()}.json"


def _latest_snapshot_path(store_id: int) -> Path:
    return _reports_dir(store_id) / "latest.json"


def _load_snapshot(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_yesterday_snapshot(store_id: int) -> dict:
    yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
    return _load_snapshot(_snapshot_path_for_date(store_id, yesterday))


def _save_result_snapshots(store_id: int, payload: dict) -> None:
    today = datetime.now(timezone.utc).date()
    dated_path = _snapshot_path_for_date(store_id, today)
    latest_path = _latest_snapshot_path(store_id)
    serialized = json.dumps(payload, indent=2)
    dated_path.write_text(serialized, encoding="utf-8")
    latest_path.write_text(serialized, encoding="utf-8")


def _empty_state() -> dict:
    return {"completed_actions": [], "action_lifecycle": {}}


def _load_state(store_id: int) -> dict:
    path = _state_path(store_id)
    if not path.exists():
        return _empty_state()
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _empty_state()
    if "completed_actions" not in state or not isinstance(state.get("completed_actions"), list):
        state["completed_actions"] = []
    if "action_lifecycle" not in state or not isinstance(state.get("action_lifecycle"), dict):
        state["action_lifecycle"] = {}
    return state


def _save_state(store_id: int, state: dict) -> None:
    _state_path(store_id).write_text(json.dumps(state, indent=2), encoding="utf-8")


def _store_snapshot_metrics(store_id: int) -> dict[str, float]:
    summary = build_summary(store_id)
    trend = ((summary.get("revenue") or {}).get("trend") or {})
    return {
        "orders_7d": float(trend.get("current_7d_orders") or 0.0),
        "revenue_7d": float(trend.get("current_7d_net_revenue") or 0.0),
    }


def _compute_normalized_delta(current_value: float, baseline_value: float) -> float:
    if baseline_value == 0:
        return float(current_value)
    return (float(current_value) - float(baseline_value)) / max(1.0, abs(float(baseline_value)))


def _build_delta_payload(before: dict[str, float], after: dict[str, float]) -> dict[str, dict[str, float] | float]:
    raw_orders = round(float(after["orders_7d"]) - float(before["orders_7d"]), 2)
    raw_revenue = round(float(after["revenue_7d"]) - float(before["revenue_7d"]), 2)
    normalized_orders = round(_compute_normalized_delta(float(after["orders_7d"]), float(before["orders_7d"])), 4)
    normalized_revenue = round(_compute_normalized_delta(float(after["revenue_7d"]), float(before["revenue_7d"])), 4)
    impact_score = round((0.4 * normalized_orders) + (0.6 * normalized_revenue), 4)
    return {
        "raw_delta": {"orders_7d": raw_orders, "revenue_7d": raw_revenue},
        "normalized_delta": {"orders_7d": normalized_orders, "revenue_7d": normalized_revenue},
        "impact_score": impact_score,
    }


def _estimated_after_for_action(baseline: dict[str, float], action: ActionResponse | None) -> dict[str, float]:
    if action is None:
        return {"orders_7d": float(baseline["orders_7d"]), "revenue_7d": float(baseline["revenue_7d"])}
    after = {"orders_7d": float(baseline["orders_7d"]), "revenue_7d": float(baseline["revenue_7d"])}
    metric = action.expected_result.metric
    if metric == "orders_7d":
        after["orders_7d"] = float(action.expected_result.target)
    elif metric == "revenue_7d":
        after["revenue_7d"] = float(action.expected_result.target)
    return after


def _infer_action_type(action: ActionResponse) -> str:
    metric = str(action.expected_result.metric).strip().lower()
    title = action.title.lower()
    context = action.context.lower()
    text = f"{title} {context}"
    if "inventory" in text or "sku" in text:
        return "inventory"
    if "return" in text or "refund" in text:
        return "returns"
    if "ads" in text or "ad " in text or "marketing" in text:
        return "acquisition"
    if "checkout" in text or "abandon" in text:
        return "conversion"
    if metric == "revenue_7d":
        return "revenue"
    return "operations"


def _harden_action_title(raw_title: str, daily_loss: float) -> str:
    title = str(raw_title).strip().lower()
    if not title:
        title = "revenue leak"
    if "inventory" in title:
        short_action = "STOP DAILY CASH LOSS"
    elif "return" in title or "refund" in title:
        short_action = "PREVENT RETURN LOSSES"
    elif "customer" in title or "churn" in title:
        short_action = "RECOVER LOST CUSTOMERS"
    elif "ad" in title or "marketing" in title:
        short_action = "STOP AD CASH DRAIN"
    else:
        short_action = "STOP CASH LEAK"
    return f"{short_action} (${round(float(daily_loss), 2):.2f}/DAY)"


def _action_consequence(action_type: str) -> str:
    consequences = {
        "inventory": "Dead inventory is draining profit",
        "returns": "Returns are eroding margin every day",
        "acquisition": "Unprofitable traffic is burning cash",
        "conversion": "Checkout friction is blocking revenue capture",
        "revenue": "Revenue opportunities are being left unclaimed",
        "operations": "Operational gaps are leaking cash",
    }
    return consequences.get(action_type, consequences["operations"])


def _primary_entity_from_targets(targets: list[str]) -> str:
    if not targets:
        return ""
    first = str(targets[0] or "").strip()
    if not first:
        return ""
    return first.split(" — ", 1)[0].strip()


def _action_system_steps(action_type: str, *, targets: list[str]) -> list[dict[str, object]]:
    """
    Translation layer: concrete, breadcrumb click-path steps per system.
    """
    entity = _primary_entity_from_targets(targets) or "listed items"
    sku_hint = "listed SKUs"

    shopify_steps: list[str] = []
    ads_steps: list[str] = []
    crm_steps: list[str] = []

    if action_type == "inventory":
        shopify_steps = [
            f"Shopify → Products → Discounts → Create 15% discount for {sku_hint}",
            f"Shopify → Bundles / Apps → Create bundle offer for dead inventory {sku_hint}",
            "Shopify → Products → Inventory → Verify on-hand quantity + adjust if needed",
        ]
        ads_steps = [
            f"Ads Manager → Pause campaigns promoting {sku_hint} until sell-through improves",
        ]
    elif action_type == "returns":
        shopify_steps = [
            f"Shopify → Products → {entity} → Update description (fit, sizing, materials) to reduce returns",
            f"Shopify → Orders → Refunds/Returns → Review return reasons for {entity}",
        ]
        ads_steps = [
            f"Ads Manager → Pause campaign for {entity}",
            f"Ads Manager → Exclude {entity} from prospecting ad sets until return rate improves",
        ]
        crm_steps = [
            f"Email/CRM → Automation → Post-purchase flow → Add sizing/fit guidance for {entity}",
        ]
    elif action_type == "acquisition":
        shopify_steps = [
            "Shopify → Analytics → Reports → Check conversion rate by landing page/product",
        ]
        ads_steps = [
            "Ads Manager → Campaigns → Sort by CPA/ROAS → Pause worst performers",
            "Ads Manager → Ad sets → Remove high-CAC audiences and shift budget to profitable sets",
        ]
    elif action_type == "conversion":
        shopify_steps = [
            "Shopify → Settings → Checkout → Review shipping, payments, and checkout branding",
            "Shopify → Analytics → Checkout behavior → Identify the biggest drop-off step",
        ]
        ads_steps = [
            "Ads Manager → Retargeting → Ensure abandoned checkout retargeting is running",
        ]
        crm_steps = [
            "Email/CRM → Flows → Abandoned checkout → Enable and verify send timing (1h / 12h / 24h)",
        ]
    elif action_type == "revenue":
        shopify_steps = [
            "Shopify → Customers → Segments → Create segment for repeat buyers / high intent",
            "Shopify → Products → Discounts → Create targeted offer (code or automatic)",
        ]
        ads_steps = [
            "Ads Manager → Retargeting → Build audience from engaged visitors / add-to-cart users",
        ]
        crm_steps = [
            "Email/CRM → Campaigns → Send offer to segment (repeat buyers outside top spenders)",
        ]
    else:  # operations
        shopify_steps = [
            "Shopify → Analytics → Reports → Identify the biggest daily loss driver",
            "Shopify → Products / Orders → Execute the specific fix on the flagged items",
        ]
        ads_steps = [
            "Ads Manager → Pause spend on any campaign tied to the loss driver",
        ]

    systems: list[dict[str, object]] = [
        {"system": "Shopify", "steps": shopify_steps},
        {"system": "Ads platform", "steps": ads_steps},
    ]
    if crm_steps:
        systems.append({"system": "Email/CRM", "steps": crm_steps})
    return systems


def _action_execution(action_type: str, execute_command: str) -> dict[str, str | list[str]]:
    command = str(execute_command).strip()
    defaults = {
        "inventory": (
            "Apply discount or bundle to move inventory",
            ["Bundle with top-selling product", "Run limited-time promotion"],
        ),
        "returns": (
            "Reduce return drivers with product clarity updates",
            ["Add fit and care guidance", "Adjust fulfillment quality checks"],
        ),
        "acquisition": (
            "Stop spend on low-converting traffic sources",
            ["Shift budget to profitable campaigns", "Pause high-CAC ad sets"],
        ),
        "conversion": (
            "Fix checkout friction to recover abandoned demand",
            ["Improve payment trust cues", "Optimize shipping visibility at checkout"],
        ),
        "revenue": (
            "Launch targeted revenue recovery campaign",
            ["Offer retention incentives", "Run urgency-based merchandising test"],
        ),
        "operations": (
            "Execute the highest-value corrective action now",
            ["Prioritize top-loss root cause", "Run a 7-day recovery sprint"],
        ),
    }
    primary, alternatives = defaults.get(action_type, defaults["operations"])
    if command:
        primary = command
    return {"primary": primary, "alternatives": alternatives}


def _operational_outcome(action_type: str) -> str:
    outcomes = {
        "inventory": "Convert non-performing assets into revenue-generating units",
        "returns": "Reduce avoidable return leakage and protect contribution margin",
        "acquisition": "Reallocate spend into channels with profitable conversion",
        "conversion": "Convert stalled checkout intent into captured orders",
        "revenue": "Increase monetized demand from existing traffic and customers",
        "operations": "Remove operational blockers that suppress revenue realization",
    }
    return outcomes.get(action_type, outcomes["operations"])


def _build_enriched_action(action: ActionResponse) -> dict:
    action_type = _infer_action_type(action)
    weekly_loss_projection = round(float(action.daily_loss) * 7.0, 2)
    hardened_title = _harden_action_title(action.title, float(action.daily_loss))
    execution = _action_execution(action_type, action.execute_command)
    targets = [str(t).strip() for t in action.targets if str(t).strip()] or ["Recover measurable revenue within 7 days"]
    systems = _action_system_steps(action_type, targets=targets)
    return {
        "id": str(action.id),
        "title": hardened_title,
        "type": action_type,
        "value": round(float(action.value), 2),
        "daily_loss": round(float(action.daily_loss), 2),
        "weekly_loss_projection": weekly_loss_projection,
        "context": str(action.context).strip() or "Revenue leakage detected and requires immediate correction.",
        "targets": targets,
        "execution": {
            "primary": str(execution["primary"]).strip() or "Execute highest-priority recovery action immediately",
            "alternatives": [str(x).strip() for x in list(execution["alternatives"]) if str(x).strip()],
        },
        "systems": systems,
        "expected_outcome": {
            "financial_recovery": round(float(action.value), 2),
            "message": f"Recover up to ${round(float(action.value), 2):.2f} by fixing this issue",
        },
        "risk_if_ignored": {
            "weekly_loss": weekly_loss_projection,
            "message": f"You will lose approximately ${weekly_loss_projection:.2f} in the next 7 days if no action is taken",
        },
        "consequence": _action_consequence(action_type),
        "decision": "EXECUTE NOW / DELAY = LOSS",
    }


def _main_cause_from_driver(primary_driver: str) -> str:
    mapping = {
        "inventory": "INVENTORY IMBALANCE",
        "returns": "RETURNS PRESSURE",
        "acquisition": "ACQUISITION SPEND LEAK",
        "conversion": "CHECKOUT CONVERSION LEAK",
        "revenue": "REVENUE CAPTURE GAP",
        "operations": "OPERATIONAL REVENUE LEAK",
    }
    return mapping.get(str(primary_driver).strip().lower(), "OPERATIONAL REVENUE LEAK")


def _write_local_report(store_id: int, payload: dict) -> None:
    report_path = (Path("reports") / str(store_id) / "latest_results_report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _extract_snapshot_metrics(snapshot: dict) -> tuple[float, float, float]:
    system_impact = snapshot.get("system_impact", {}) if isinstance(snapshot, dict) else {}
    inaction_risk = snapshot.get("inaction_risk", {}) if isinstance(snapshot, dict) else {}
    risk = snapshot.get("risk", {}) if isinstance(snapshot, dict) else {}
    revenue = round(float(system_impact.get("total_revenue_recovered_7d") or 0.0), 2)
    loss = round(float(inaction_risk.get("weekly_loss") or 0.0), 2)
    risk_value = round(float(risk.get("weekly_loss_projection") or 0.0), 2)
    return revenue, loss, risk_value


def _trend_state_from_delta(*, revenue_change: float, loss_change: float, risk_change: float) -> str:
    epsilon = 0.01
    if loss_change > epsilon or revenue_change < -epsilon or risk_change > epsilon:
        return "worsening"
    if loss_change < -epsilon or revenue_change > epsilon or risk_change < -epsilon:
        return "improving"
    return "stable"


def _build_daily_insight(*, trend_state: str, revenue_change: float, loss_change: float, risk_change: float, baseline: bool) -> dict:
    if baseline:
        msg = "Baseline established. Future reports will track performance changes."
        return {"message": msg, "key_change": msg}
    if trend_state == "worsening":
        if loss_change > 0.01:
            return {
                "message": f"Store loss increased by ${abs(loss_change):.2f} versus yesterday.",
                "key_change": "Loss exposure is rising and requires faster execution.",
            }
        if revenue_change < -0.01:
            return {
                "message": f"Recovered revenue dropped by ${abs(revenue_change):.2f} versus yesterday.",
                "key_change": "Revenue recovery momentum weakened today.",
            }
        return {
            "message": f"Risk exposure increased by ${abs(risk_change):.2f} versus yesterday.",
            "key_change": "Operational risk pressure is higher today.",
        }
    if trend_state == "improving":
        if loss_change < -0.01:
            return {
                "message": f"Store loss decreased by ${abs(loss_change):.2f} versus yesterday.",
                "key_change": "Loss pressure improved today.",
            }
        if revenue_change > 0.01:
            return {
                "message": f"Recovered revenue improved by ${abs(revenue_change):.2f} versus yesterday.",
                "key_change": "Revenue recovery momentum improved today.",
            }
        return {
            "message": f"Risk exposure decreased by ${abs(risk_change):.2f} versus yesterday.",
            "key_change": "Operational risk pressure reduced today.",
        }
    return {
        "message": "Today is stable versus yesterday with minimal financial movement.",
        "key_change": "No significant day-over-day change detected.",
    }


def _format_signed_money(value: float) -> str:
    if value > 0:
        return f"+${value:.2f}"
    if value < 0:
        return f"-${abs(value):.2f}"
    return "$0.00"


def _build_daily_comparison(*, revenue_change: float, loss_change: float, baseline: bool) -> dict:
    if baseline:
        msg = "First tracking day — baseline established"
        return {
            "title": msg,
            "loss_change_line": "",
            "revenue_change_line": "",
            "continuity_memory": msg,
            "baseline_mode": True,
        }
    return {
        "title": "DAILY CHANGE vs YESTERDAY",
        "loss_change_line": f"{_format_signed_money(loss_change)} change in loss",
        "revenue_change_line": f"{_format_signed_money(revenue_change)} change in revenue recovery",
        "continuity_memory": "Comparing today against previous day performance",
        "baseline_mode": False,
    }


def _generate_local_pdf_report(store_id: int, report_payload: dict) -> str:
    output_dir = str(Path("reports") / str(store_id))
    return create_report_pdf(report_payload, output_dir=output_dir, store_id=store_id)


def _to_canonical_actions(store_id: int) -> list[ActionResponse]:
    summary = build_summary(store_id)
    raw_actions = build_structured_actions(summary, max_actions=5)
    baseline = _store_snapshot_metrics(store_id)
    actions: list[ActionResponse] = []
    for idx, raw in enumerate(raw_actions, start=1):
        er = raw.get("expected_result") or {}
        target_min = float(er.get("target_min") or 0.0)
        target_max = float(er.get("target_max") or 0.0)
        target = target_max if target_max > 0 else target_min
        expected_metric = str(er.get("metric") or "orders_7d")
        baseline_orders = float(baseline.get("orders_7d") or 0.0)
        baseline_revenue = float(baseline.get("revenue_7d") or 0.0)
        expected_after = {"orders_7d": baseline_orders, "revenue_7d": baseline_revenue}
        if expected_metric == "orders_7d":
            expected_after["orders_7d"] = target
        elif expected_metric == "revenue_7d":
            expected_after["revenue_7d"] = target
        delta_payload = _build_delta_payload({"orders_7d": baseline_orders, "revenue_7d": baseline_revenue}, expected_after)
        normalized_delta = delta_payload["normalized_delta"]
        normalized_impact_weight = round(
            (float(normalized_delta["orders_7d"]) + float(normalized_delta["revenue_7d"])) / 2.0, 4
        )
        score = round(
            (float(raw.get("value") or 0.0) + (float(raw.get("daily_loss") or 0.0) * 7.0)) * (1.0 + normalized_impact_weight),
            4,
        )
        actions.append(
            ActionResponse(
                id=f"action_{idx}",
                title=str(raw.get("title") or ""),
                value=float(raw.get("value") or 0.0),
                daily_loss=float(raw.get("daily_loss") or 0.0),
                priority_score=score,
                priority_ratio=1.0,
                priority_explanation=f"Why this is ranked #{idx}: projected normalized impact weight {normalized_impact_weight:.2f}",
                rank=idx,
                context=str(raw.get("context") or ""),
                targets=[str(t) for t in (raw.get("targets") or []) if str(t).strip()],
                execute_command=str(raw.get("execute_command") or ""),
                goal=str(raw.get("goal") or ""),
                measured_by=[str(m) for m in (raw.get("measured_by") or []) if str(m).strip()],
                expected_result=ExpectedResult(
                    metric=expected_metric,
                    baseline=float(er.get("baseline") or 0.0),
                    target=float(target),
                    time_window_days=7,
                ),
                baseline_metrics=BaselineMetrics(
                    orders_7d=float(baseline.get("orders_7d") or 0.0),
                    revenue_7d=float(baseline.get("revenue_7d") or 0.0),
                ),
                normalized_impact_weight=normalized_impact_weight,
            )
        )
    actions.sort(key=lambda a: a.priority_score, reverse=True)
    for idx, action in enumerate(actions, start=1):
        action.rank = idx
    for idx, action in enumerate(actions):
        next_score = actions[idx + 1].priority_score if idx + 1 < len(actions) else action.priority_score
        ratio = (action.priority_score / next_score) if next_score > 0 else 1.0
        action.priority_ratio = round(ratio, 2)
        action.priority_explanation = f"Why this is ranked #{action.rank}: {ratio:.2f} times higher impact than next action"
    return actions


def _ensure_action_started(state: dict, action_id: str) -> str:
    lifecycle = state.get("action_lifecycle", {})
    row = lifecycle.get(action_id, {})
    started = str(row.get("timestamp_started") or "").strip()
    if not started:
        started = _utc_now_iso()
        lifecycle[action_id] = {"timestamp_started": started}
        state["action_lifecycle"] = lifecycle
    return started


def _validated_after(timestamp_completed: str) -> bool:
    completed_at = _parse_utc(timestamp_completed)
    return datetime.now(timezone.utc) >= (completed_at + timedelta(hours=24))


@app.get("/api/actions")
def api_actions(store_id: int = 1) -> list[ActionResponse]:
    actions = _to_canonical_actions(store_id)
    state = _load_state(store_id)
    for action in actions:
        _ensure_action_started(state, action.id)
    _save_state(store_id, state)
    return actions


@app.post("/api/complete-action")
def api_complete_action(payload: CompleteActionRequest, store_id: int = 1) -> dict:
    actions = api_actions(store_id)
    action = next((a for a in actions if a.id == payload.action_id), None)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    state = _load_state(store_id)
    completed = list(state.get("completed_actions", []))
    if any(str(x.get("action_id")) == payload.action_id for x in completed):
        return {"status": "already_completed", "action_id": payload.action_id}

    timestamp_started = _ensure_action_started(state, payload.action_id)
    baseline = _store_snapshot_metrics(store_id)
    completed.append(
        {
            "action_id": payload.action_id,
            "title": action.title,
            "timestamp_started": timestamp_started,
            "timestamp_completed": _utc_now_iso(),
            "baseline_metrics": baseline,
            "value": float(action.value),
            "daily_loss": float(action.daily_loss),
        }
    )
    state["completed_actions"] = completed
    _save_state(store_id, state)
    return {"status": "completed", "action_id": payload.action_id}


@app.get("/api/results")
def api_results(store_id: int = 1) -> dict:
    actions = _to_canonical_actions(store_id)
    state = _load_state(store_id)
    completed = list(state.get("completed_actions", []))
    total_revenue_recovered_7d = round(sum(float(x.get("value") or 0.0) for x in completed), 2)
    total_loss_prevented_7d = round(sum(float(x.get("daily_loss") or 0.0) * 7.0 for x in completed), 2)
    actions_completed = len(completed)
    roi_efficiency_score = round(
        ((total_revenue_recovered_7d + total_loss_prevented_7d) / actions_completed) if actions_completed > 0 else 0.0,
        4,
    )
    enriched_actions = [_build_enriched_action(action) for action in actions]
    total_daily_loss = round(sum(float(x["daily_loss"]) for x in enriched_actions), 2)
    weekly_recoverable = round(sum(float(x["value"]) for x in enriched_actions), 2)
    weekly_risk = round(total_daily_loss * 7.0, 2)
    primary_driver = (
        str(max(enriched_actions, key=lambda a: float(a["daily_loss"]))["type"])
        if enriched_actions
        else "operations"
    )
    headline_primary = (
        f"YOUR STORE IS LOSING ${total_daily_loss:.2f} TODAY"
        if total_daily_loss > 0
        else "NO ACTIVE STORE LOSS DETECTED TODAY"
    )
    headline_secondary = (
        f"${total_daily_loss:.2f}/day is currently being lost due to unresolved store issues"
    )
    if total_daily_loss > 20:
        status_level = "CONFIRMED REVENUE LEAKS DETECTED"
        status_message = "Multiple operational failures are actively reducing store profitability"
    elif total_daily_loss > 0:
        status_level = "CONFIRMED REVENUE LEAKS DETECTED"
        status_message = "Multiple operational failures are actively reducing store profitability"
    else:
        status_level = "STABLE"
        status_message = "No active revenue leaks detected right now"
    report_payload = {
        "generated_at": _utc_now_iso(),
        "headline": {"primary": headline_primary, "secondary": headline_secondary},
        "status": {"level": status_level, "message": status_message},
        "execution_required": {
            "title": "EXECUTION REQUIRED",
            "message": "Failure to act results in compounding daily revenue loss",
        },
        "main_cause": _main_cause_from_driver(primary_driver),
        "inaction_risk": {
            "weekly_loss": weekly_risk,
            "message": f"If no action is taken, you will lose approximately ${weekly_risk:.2f} in the next 7 days",
        },
        "execution_instruction": {
            "headline": "IMMEDIATE EXECUTION REQUIRED",
            "line_1": "Start with ACTION #1",
            "line_2": "Do NOT delay ACTION #2",
        },
        "actions": enriched_actions,
        "system_impact": {
            "total_revenue_recovered_7d": total_revenue_recovered_7d,
            "total_loss_prevented_7d": total_loss_prevented_7d,
            "roi_efficiency_score": roi_efficiency_score,
        },
        "risk": {
            "weekly_loss_projection": weekly_risk,
            "primary_driver": f"ROOT CAUSE IDENTIFIED: {_main_cause_from_driver(primary_driver)}",
        },
        "execution_outcome_heading": "EXECUTION OUTCOME (PROJECTED IMPACT):",
        "final_warning": "Continued inaction will maintain the current loss rate.",
    }
    for idx, enriched_action in enumerate(report_payload["actions"]):
        if idx == 0:
            enriched_action["hierarchy_label"] = "HIGHEST IMPACT ACTION — EXECUTE FIRST"
            enriched_action["priority_level"] = "primary"
        elif idx == 1:
            enriched_action["hierarchy_label"] = "SECONDARY ISSUE — ADDRESS AFTER ACTION #1"
            enriched_action["priority_level"] = "secondary"
        else:
            enriched_action["hierarchy_label"] = "ADDITIONAL LEAK — CONTAIN FINANCIAL RISK"
            enriched_action["priority_level"] = "additional"

    yesterday_snapshot = _load_yesterday_snapshot(store_id)
    has_yesterday = bool(yesterday_snapshot)
    today_revenue, today_loss, today_risk = _extract_snapshot_metrics(report_payload)
    if has_yesterday:
        prev_revenue, prev_loss, prev_risk = _extract_snapshot_metrics(yesterday_snapshot)
    else:
        prev_revenue, prev_loss, prev_risk = (today_revenue, today_loss, today_risk)

    daily_delta = {
        "revenue_change": round(today_revenue - prev_revenue, 2),
        "loss_change": round(today_loss - prev_loss, 2),
        "risk_change": round(today_risk - prev_risk, 2),
    }
    trend_state = _trend_state_from_delta(
        revenue_change=float(daily_delta["revenue_change"]),
        loss_change=float(daily_delta["loss_change"]),
        risk_change=float(daily_delta["risk_change"]),
    )
    if not has_yesterday:
        daily_delta = {"revenue_change": 0.0, "loss_change": 0.0, "risk_change": 0.0}
        trend_state = "baseline (first tracking day)"
    daily_insight = _build_daily_insight(
        trend_state=trend_state,
        revenue_change=float(daily_delta["revenue_change"]),
        loss_change=float(daily_delta["loss_change"]),
        risk_change=float(daily_delta["risk_change"]),
        baseline=not has_yesterday,
    )
    daily_comparison = _build_daily_comparison(
        revenue_change=float(daily_delta["revenue_change"]),
        loss_change=float(daily_delta["loss_change"]),
        baseline=not has_yesterday,
    )

    prev_actions = yesterday_snapshot.get("actions", []) if has_yesterday else []
    prev_type_loss: dict[str, float] = {}
    for item in prev_actions:
        action_type = str((item or {}).get("type") or "").strip().lower()
        if not action_type:
            continue
        prev_type_loss[action_type] = prev_type_loss.get(action_type, 0.0) + float((item or {}).get("daily_loss") or 0.0)
    for enriched_action in report_payload["actions"]:
        action_type = str(enriched_action.get("type") or "").strip().lower()
        previous_loss = round(float(prev_type_loss.get(action_type, 0.0)), 2) if has_yesterday else 0.0
        current_loss = round(float(enriched_action.get("daily_loss") or 0.0), 2)
        enriched_action["previous_impact"] = {
            "same_type_last_day_loss": previous_loss,
            "change": round(current_loss - previous_loss, 2) if has_yesterday else 0.0,
        }

    report_payload["daily_delta"] = daily_delta
    report_payload["trend_state"] = trend_state
    report_payload["daily_insight"] = daily_insight
    report_payload["daily_comparison"] = daily_comparison

    _generate_local_pdf_report(store_id, report_payload)
    response = {
        "generated_at": report_payload["generated_at"],
        "headline": report_payload["headline"],
        "status": report_payload["status"],
        "execution_required": report_payload["execution_required"],
        "main_cause": report_payload["main_cause"],
        "inaction_risk": report_payload["inaction_risk"],
        "execution_instruction": report_payload["execution_instruction"],
        "actions": report_payload["actions"],
        "system_impact": report_payload["system_impact"],
        "risk": report_payload["risk"],
        "execution_outcome_heading": report_payload["execution_outcome_heading"],
        "final_warning": report_payload["final_warning"],
        "daily_delta": report_payload["daily_delta"],
        "trend_state": report_payload["trend_state"],
        "daily_insight": report_payload["daily_insight"],
        "daily_comparison": report_payload["daily_comparison"],
        "continuity_memory": report_payload["daily_comparison"]["continuity_memory"],
    }
    _write_local_report(store_id, response)
    _save_result_snapshots(store_id, response)
    return response


@app.get("/api/proof")
def api_proof(store_id: int = 1) -> list[dict]:
    results = api_results(store_id)
    proof_rows: list[dict] = []
    for row in results.get("before_after_comparison", []):
        status = str(row.get("status") or "pending_validation")
        before = row.get("before") or {"orders_7d": 0.0, "revenue_7d": 0.0}
        after = row.get("after") or {"orders_7d": 0.0, "revenue_7d": 0.0}
        delta = row.get("delta") or {"orders_7d": 0.0, "revenue_7d": 0.0}
        is_valid = status == "validated"
        predicted_orders = max(float(before.get("orders_7d") or 0.0) * 0.15, 1.0)
        predicted_revenue = max(float(before.get("revenue_7d") or 0.0) * 0.12, 25.0)
        actual_orders = float(delta.get("orders_7d") or 0.0)
        actual_revenue = float(delta.get("revenue_7d") or 0.0)
        confidence_score = 0.0
        if is_valid:
            order_ratio = (actual_orders / predicted_orders) if predicted_orders > 0 else 0.0
            revenue_ratio = (actual_revenue / predicted_revenue) if predicted_revenue > 0 else 0.0
            confidence_score = max(min((order_ratio + revenue_ratio) * 50.0, 100.0), 0.0)
        proof_rows.append(
            {
                "action_id": str(row.get("action_id") or ""),
                "is_valid": is_valid,
                "confidence_score": round(confidence_score, 2),
                "predicted_delta": {"orders": round(predicted_orders, 2), "revenue": round(predicted_revenue, 2)},
                "actual_delta": {"orders": round(actual_orders, 2), "revenue": round(actual_revenue, 2)},
                "roi_confirmed": bool(is_valid and (actual_orders > 0 or actual_revenue > 0)),
            }
        )
    return proof_rows
