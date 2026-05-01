from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from config.logging_config import get_logger
from db.queries import (
    count_new_customers_in_window,
    create_task,
    get_due_task_evaluations,
    get_task_by_fingerprint,
    get_task_by_id_for_store,
    get_tasks_for_report,
    get_tasks_needing_reminders,
    list_tasks_for_store,
    set_task_actual_impact,
    touch_task_reminder,
    update_task_metadata,
    update_task_status,
)

logger = get_logger(__name__)

SEVERITY_TO_PRIORITY = {"high": "high", "medium": "medium", "low": "low"}
ALLOWED_STATUS = {"pending", "in_progress", "completed", "ignored"}


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _task_type_from_insight(insight: dict) -> str:
    title = (insight.get("title") or "").lower()
    if "churn" in title:
        return "win_back"
    if "return" in title:
        return "pause_sku"
    if "concentration" in title or "high-value" in title:
        return "acquisition"
    if "dead inventory" in title:
        return "dead_inventory"
    if "discount" in title:
        return "discount_audit"
    if "duplicate" in title:
        return "duplicate_audit"
    return "general"


def _entity_from_insight(insight: dict) -> str:
    if insight.get("primary_entity_id") is not None:
        return str(insight["primary_entity_id"])
    if insight.get("product_id") is not None:
        return str(insight["product_id"])
    title = (insight.get("title") or "").lower()
    if "churn" in title:
        return "churn_90d"
    return title.replace(" ", "_")[:64] or "unknown"


def _fingerprint(store_id: int, task_type: str, primary_entity_id: str) -> str:
    raw = f"{store_id}|{task_type}|{primary_entity_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _current_metric_value(task_type: str, summary: dict, task: dict | None = None) -> float:
    if task_type == "win_back":
        return float(len(summary.get("customers", {}).get("churned", [])))
    if task_type == "pause_sku":
        product_id = str((task or {}).get("primary_entity_id") or "")
        for p in summary.get("revenue", {}).get("high_return_rate", []):
            if str(p.get("product_id")) == product_id:
                return _safe_float(p.get("return_rate"))
        return 0.0
    if task_type == "acquisition":
        health = summary.get("customers", {}).get("health", {})
        return _safe_float(health.get("repeat_customers_last_30d"))
    return _safe_float(summary.get("revenue", {}).get("summary", {}).get("net_revenue"))


def _ignored_should_reopen(existing_task: dict, summary: dict) -> bool:
    task_type = (existing_task.get("type") or "").lower()
    previous = _safe_float(existing_task.get("baseline_metric"))
    current = _current_metric_value(task_type, summary, existing_task)
    if previous <= 0:
        return current > 0
    return current >= previous * 1.2


def sync_tasks_from_summary(store_id: int, summary: dict) -> list[dict]:
    upserted: list[dict] = []
    for insight in summary.get("insights", []):
        task_type = _task_type_from_insight(insight)
        entity_id = _entity_from_insight(insight)
        fingerprint = _fingerprint(store_id, task_type, entity_id)
        existing = get_task_by_fingerprint(store_id, fingerprint)

        priority = SEVERITY_TO_PRIORITY.get((insight.get("severity") or "medium").lower(), "medium")
        expected_impact = _safe_float(insight.get("potential_value"))
        metadata = {
            "impact_type": insight.get("impact_type"),
            "category": insight.get("category"),
            "source_title": insight.get("title"),
            "action_cta": insight.get("action_cta"),
        }
        due_at = datetime.now(timezone.utc) + timedelta(days=1)

        if existing and existing.get("status") in {"pending", "in_progress"}:
            updated = update_task_metadata(
                task_id=int(existing["id"]),
                store_id=store_id,
                title=str(insight.get("title") or "Action Required"),
                description=str(insight.get("action") or "Review and execute."),
                priority=priority,
                expected_impact=expected_impact,
                due_at=due_at,
                metadata_json=json.dumps(metadata),
            )
            upserted.append(updated)
            continue

        if existing and existing.get("status") == "ignored":
            if _ignored_should_reopen(existing, summary):
                reopened = update_task_status(task_id=int(existing["id"]), store_id=store_id, status="pending")
                if reopened:
                    updated = update_task_metadata(
                        task_id=int(existing["id"]),
                        store_id=store_id,
                        title=str(insight.get("title") or "Action Required"),
                        description=str(insight.get("action") or "Review and execute."),
                        priority=priority,
                        expected_impact=expected_impact,
                        due_at=due_at,
                        metadata_json=json.dumps(metadata),
                    )
                    upserted.append(updated)
            continue

        if existing and existing.get("status") == "completed":
            # Keep history; do not recreate unless metric worsens significantly.
            if _ignored_should_reopen({**existing, "status": "ignored"}, summary):
                created = create_task(
                    store_id=store_id,
                    task_type=task_type,
                    title=str(insight.get("title") or "Action Required"),
                    description=str(insight.get("action") or "Review and execute."),
                    status="pending",
                    priority=priority,
                    due_at=due_at,
                    expected_impact=expected_impact,
                    fingerprint=fingerprint,
                    primary_entity_id=entity_id,
                    metadata_json=json.dumps(metadata),
                )
                upserted.append(created)
            continue

        created = create_task(
            store_id=store_id,
            task_type=task_type,
            title=str(insight.get("title") or "Action Required"),
            description=str(insight.get("action") or "Review and execute."),
            status="pending",
            priority=priority,
            due_at=due_at,
            expected_impact=expected_impact,
            fingerprint=fingerprint,
            primary_entity_id=entity_id,
            metadata_json=json.dumps(metadata),
        )
        upserted.append(created)
    return upserted


def transition_task_status(store_id: int, task_id: int, status: str, summary: dict | None = None) -> dict | None:
    if status not in ALLOWED_STATUS:
        raise ValueError(f"Invalid status: {status}")
    existing = get_task_by_id_for_store(task_id, store_id)
    if not existing:
        return None

    prev = str(existing.get("status") or "pending")
    allowed = {
        # Auto-verification can complete tasks directly from pending when
        # the leak disappears before a manual in_progress transition occurs.
        "pending": {"in_progress", "completed", "ignored"},
        "in_progress": {"completed", "ignored"},
        "completed": set(),
        "ignored": set(),
    }
    if status != prev and status not in allowed.get(prev, set()):
        raise ValueError(f"Invalid transition: {prev} -> {status}")

    completed_at = None
    due_at = None
    baseline_metric = None
    if status == "completed":
        now = datetime.now(timezone.utc)
        completed_at = now
        due_at = now + timedelta(days=3)
        if summary is not None:
            baseline_metric = _current_metric_value(str(existing.get("type") or ""), summary, existing)

    return update_task_status(
        task_id=task_id,
        store_id=store_id,
        status=status,
        completed_at=completed_at,
        due_at=due_at,
        baseline_metric=baseline_metric,
    )


def evaluate_completed_task_impacts(store_id: int, summary: dict) -> list[dict]:
    evaluated: list[dict] = []
    for task in get_due_task_evaluations(store_id):
        baseline = _safe_float(task.get("baseline_metric"))
        task_type = str(task.get("type") or "")
        completion = task.get("completed_at")
        if not completion:
            continue

        impact = 0.0
        if task_type == "win_back":
            start_at = completion + timedelta(days=3)
            end_at = completion + timedelta(days=7)
            impact = float(count_new_customers_in_window(store_id, start_at, end_at))
        elif task_type == "pause_sku":
            current = _current_metric_value(task_type, summary, task)
            impact = baseline - current
        elif task_type == "acquisition":
            current = _current_metric_value(task_type, summary, task)
            impact = current - baseline
        else:
            current_net = _safe_float(summary.get("revenue", {}).get("summary", {}).get("net_revenue"))
            impact = current_net - baseline

        set_task_actual_impact(int(task["id"]), impact, store_id=store_id)
        task["actual_impact"] = impact
        evaluated.append(task)
    return evaluated


def auto_verify_tasks_from_summary(store_id: int, summary: dict) -> list[dict]:
    verified: list[dict] = []
    current_high_return_ids = {
        str(p.get("product_id"))
        for p in summary.get("revenue", {}).get("high_return_rate", [])
        if p.get("product_id") is not None
    }
    for task in list_tasks_for_store(store_id, limit=500):
        if task.get("status") not in {"pending", "in_progress"}:
            continue
        if str(task.get("type") or "") != "pause_sku":
            continue
        product_id = str(task.get("primary_entity_id") or "")
        if product_id and product_id not in current_high_return_ids:
            updated = transition_task_status(store_id, int(task["id"]), "completed", summary=summary)
            if updated:
                verified.append(updated)
    return verified


def build_report_task_sections(store_id: int, summary: dict) -> dict:
    _ = summary
    tasks = get_tasks_for_report(store_id)
    status_order = {"pending": 0, "in_progress": 1, "completed": 2, "ignored": 3}
    ordered = sorted(
        tasks,
        key=lambda t: (
            status_order.get(str(t.get("status") or "pending"), 9),
            -_safe_float(t.get("expected_impact")),
            str(t.get("title") or "").lower(),
            int(t.get("id") or 0),
        ),
    )
    return {"tasks": ordered}


def collect_due_reminders(store_id: int) -> list[dict]:
    reminders = get_tasks_needing_reminders(store_id)
    for task in reminders:
        touch_task_reminder(int(task["id"]), store_id=store_id)
    return reminders


def list_store_tasks(store_id: int, limit: int = 100) -> list[dict]:
    return list_tasks_for_store(store_id, limit=limit)
