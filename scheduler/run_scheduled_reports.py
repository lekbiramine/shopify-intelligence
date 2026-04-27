import time
from datetime import datetime, timezone
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

# Ensure repo root is importable when running as a script
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config.logging_config import get_logger, setup_logging
from db.queries import claim_report_send_slot, get_active_scheduled_stores, get_store_by_domain
from scheduler.run_pipeline import run_etl_for_store, run_reporting_for_store

setup_logging()
logger = get_logger(__name__)


def _local_hhmm(now_utc: datetime, tz_name: str) -> str:
    tz = ZoneInfo(tz_name)
    return now_utc.astimezone(tz).strftime("%H:%M")


def run_forever(poll_seconds: int = 20) -> None:
    """
    Simple scheduler loop:
    - polls active schedules
    - if store-local time matches scheduled HH:MM, sends report (enforced by 24h limiter)
    """
    logger.info("Scheduled reports worker started.")
    while True:
        try:
            now_utc = datetime.now(timezone.utc)
            stores = get_active_scheduled_stores()
            for s in stores:
                shop_domain = (s.get("shop_domain") or "").strip()
                hhmm = (s.get("report_schedule_time") or "").strip()
                tz_name = (s.get("report_timezone") or "UTC").strip() or "UTC"
                if not shop_domain or not hhmm:
                    continue

                try:
                    local_hhmm = _local_hhmm(now_utc, tz_name)
                except Exception:
                    logger.warning("Invalid timezone %s for %s, defaulting UTC", tz_name, shop_domain)
                    local_hhmm = now_utc.strftime("%H:%M")

                if local_hhmm != hhmm:
                    continue

                if not claim_report_send_slot(shop_domain):
                    continue

                store = get_store_by_domain(shop_domain) or {}
                store_id = store.get("id")
                access_token = (store.get("access_token") or "").strip()
                refresh_token = (store.get("refresh_token") or "").strip() or None
                access_token_expires_at = store.get("access_token_expires_at")
                if not store_id or not access_token:
                    logger.warning("Missing store_id/access_token for %s; skipping", shop_domain)
                    continue

                logger.info("Sending scheduled report for %s (%s %s)", shop_domain, tz_name, hhmm)
                run_etl_for_store(
                    store_id=store_id,
                    shop_domain=shop_domain,
                    access_token=access_token,
                    refresh_token=refresh_token,
                    access_token_expires_at=access_token_expires_at,
                )
                run_reporting_for_store(store_id=store_id)

        except Exception:
            logger.exception("Scheduled worker iteration failed")

        time.sleep(poll_seconds)


if __name__ == "__main__":
    run_forever()

