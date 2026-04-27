from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from analytics.summary import build_summary
from config.logging_config import setup_logging
from db.queries import get_store_by_domain, get_task_by_id_for_store
from tasks.engine import list_store_tasks, transition_task_status
from utils.shopify_auth import normalize_shop_domain


def _store_id_from_domain(shop_domain: str) -> int:
    store = get_store_by_domain(normalize_shop_domain(shop_domain)) or {}
    if not store.get("id"):
        raise RuntimeError(f"Store not found: {shop_domain}")
    return int(store["id"])


def _cmd_list(args: argparse.Namespace) -> None:
    store_id = _store_id_from_domain(args.shop_domain)
    rows = list_store_tasks(store_id, limit=args.limit)
    if not rows:
        print("No tasks found.")
        return
    for t in rows:
        print(
            f"#{t['id']} [{t['status']}] {t['priority'].upper()} {t['type']} "
            f"impact=${float(t.get('expected_impact') or 0):,.2f} title={t['title']}"
        )


def _cmd_mark(args: argparse.Namespace) -> None:
    status = args.status
    store_id = _store_id_from_domain(args.shop_domain)
    summary = None
    if status == "completed":
        task = get_task_by_id_for_store(args.task_id, store_id)
        if not task:
            raise RuntimeError(f"Task not found: {args.task_id}")
        summary = build_summary(store_id)
    updated = transition_task_status(store_id, args.task_id, status, summary=summary)
    if not updated:
        raise RuntimeError(f"Task not found: {args.task_id}")
    print(f"Task #{updated['id']} updated to {updated['status']}.")


def _cmd_show(args: argparse.Namespace) -> None:
    store_id = _store_id_from_domain(args.shop_domain)
    task = get_task_by_id_for_store(args.task_id, store_id)
    if not task:
        raise RuntimeError(f"Task not found: {args.task_id}")
    print(f"id: {task['id']}")
    print(f"store_id: {task['store_id']}")
    print(f"type: {task['type']}")
    print(f"title: {task['title']}")
    print(f"status: {task['status']}")
    print(f"priority: {task['priority']}")
    print(f"expected_impact: {float(task.get('expected_impact') or 0):,.2f}")
    print(f"actual_impact: {task.get('actual_impact')}")
    print(f"due_at: {task.get('due_at')}")
    print(f"completed_at: {task.get('completed_at')}")
    print("metadata_json:")
    print(json.dumps(task.get("metadata_json") or {}, indent=2, default=str))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Task operations for store intelligence workflow.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List tasks for a store.")
    p_list.add_argument("--shop-domain", required=True)
    p_list.add_argument("--limit", type=int, default=100)
    p_list.set_defaults(func=_cmd_list)

    p_mark = sub.add_parser("mark", help="Mark task status.")
    p_mark.add_argument("--shop-domain", required=True)
    p_mark.add_argument("--task-id", type=int, required=True)
    p_mark.add_argument("--status", choices=["in_progress", "completed", "ignored"], required=True)
    p_mark.set_defaults(func=_cmd_mark)

    p_show = sub.add_parser("show", help="Show task details and impact.")
    p_show.add_argument("--shop-domain", required=True)
    p_show.add_argument("--task-id", type=int, required=True)
    p_show.set_defaults(func=_cmd_show)
    return parser.parse_args()


def main() -> None:
    setup_logging()
    args = parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
