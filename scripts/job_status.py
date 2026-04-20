from pathlib import Path
import argparse
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config.logging_config import setup_logging
from db.queries import get_recent_job_runs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show recent job and email delivery statuses.")
    parser.add_argument("--limit", type=int, default=20, help="Number of recent runs to display")
    parser.add_argument(
        "--only-failed",
        action="store_true",
        help="Show only failed runs",
    )
    return parser.parse_args()


def main() -> None:
    setup_logging()
    args = parse_args()
    rows = get_recent_job_runs(limit=max(1, args.limit))
    if args.only_failed:
        rows = [r for r in rows if (r.get("status") or "").lower() == "failed"]

    if not rows:
        print("No matching job runs found.")
        return

    for row in rows:
        status = (row.get("status") or "").upper()
        email_state = "YES" if row.get("email_sent") else "NO"
        finished = row.get("finished_at") or "-"
        print(
            f"[{row.get('id')}] {row.get('shop_domain')} "
            f"status={status} email_sent={email_state} started={row.get('started_at')} finished={finished}"
        )
        if row.get("error_message"):
            print(f"  error: {row.get('error_message')}")


if __name__ == "__main__":
    main()
