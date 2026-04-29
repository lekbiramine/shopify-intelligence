from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from analytics.summary import build_summary
from reporting.pdf_report_v2 import build_structured_actions

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


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _state_path(store_id: int) -> Path:
    out_dir = Path("reports") / str(store_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / "action_tracking.json"


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


def _to_canonical_actions(store_id: int) -> list[ActionResponse]:
    summary = build_summary(store_id)
    raw_actions = build_structured_actions(summary, max_actions=5)
    baseline = _store_snapshot_metrics(store_id)
    actions: list[ActionResponse] = []
    scores = [float(a.get("priority_score") or 0.0) for a in raw_actions]

    for idx, raw in enumerate(raw_actions, start=1):
        er = raw.get("expected_result") or {}
        target_min = float(er.get("target_min") or 0.0)
        target_max = float(er.get("target_max") or 0.0)
        target = target_max if target_max > 0 else target_min
        score = float(raw.get("priority_score") or 0.0)
        next_score = scores[idx] if idx < len(scores) else score
        ratio = (score / next_score) if next_score > 0 else 1.0
        actions.append(
            ActionResponse(
                id=f"action_{idx}",
                title=str(raw.get("title") or ""),
                value=float(raw.get("value") or 0.0),
                daily_loss=float(raw.get("daily_loss") or 0.0),
                priority_score=score,
                priority_ratio=round(ratio, 2),
                priority_explanation=f"Why this is ranked #{idx}: {ratio:.2f} times higher impact than next action",
                rank=idx,
                context=str(raw.get("context") or ""),
                targets=[str(t) for t in (raw.get("targets") or []) if str(t).strip()],
                execute_command=str(raw.get("execute_command") or ""),
                goal=str(raw.get("goal") or ""),
                measured_by=[str(m) for m in (raw.get("measured_by") or []) if str(m).strip()],
                expected_result=ExpectedResult(
                    metric=str(er.get("metric") or "orders_7d"),
                    baseline=float(er.get("baseline") or 0.0),
                    target=float(target),
                    time_window_days=7,
                ),
                baseline_metrics=BaselineMetrics(
                    orders_7d=float(baseline.get("orders_7d") or 0.0),
                    revenue_7d=float(baseline.get("revenue_7d") or 0.0),
                ),
            )
        )
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
    state = _load_state(store_id)
    completed = list(state.get("completed_actions", []))
    snapshot = _store_snapshot_metrics(store_id)
    comparisons: list[dict] = []

    for row in completed:
        baseline = row.get("baseline_metrics", {}) or {}
        before = {
            "orders_7d": float(baseline.get("orders_7d") or 0.0),
            "revenue_7d": float(baseline.get("revenue_7d") or 0.0),
        }
        timestamp_completed = str(row.get("timestamp_completed") or "")
        if not timestamp_completed:
            status = "pending_validation"
            after = None
            delta = None
        elif _validated_after(timestamp_completed):
            status = "validated"
            after = {"orders_7d": float(snapshot["orders_7d"]), "revenue_7d": float(snapshot["revenue_7d"])}
            delta = {
                "orders_7d": round(after["orders_7d"] - before["orders_7d"], 2),
                "revenue_7d": round(after["revenue_7d"] - before["revenue_7d"], 2),
            }
        else:
            status = "pending_validation"
            after = None
            delta = None
        comparisons.append(
            {
                "action_id": str(row.get("action_id") or ""),
                "title": str(row.get("title") or ""),
                "status": status,
                "before": before,
                "after": after,
                "delta": delta,
                "timestamp_started": str(row.get("timestamp_started") or ""),
                "timestamp_completed": timestamp_completed,
            }
        )

    return {
        "completed_actions": completed,
        "before_after_comparison": comparisons,
        "total_revenue_recovered": round(sum(float(x.get("value") or 0.0) for x in completed), 2),
        "total_loss_prevented": round(sum(float(x.get("daily_loss") or 0.0) * 7.0 for x in completed), 2),
    }


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
