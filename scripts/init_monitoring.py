from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config.logging_config import get_logger, setup_logging
from db.connection import get_cursor

logger = get_logger(__name__)


CREATE_JOB_RUNS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS job_runs (
    id BIGSERIAL PRIMARY KEY,
    store_id BIGINT NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    shop_domain VARCHAR(255) NOT NULL,
    status VARCHAR(16) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    email_sent BOOLEAN NOT NULL DEFAULT FALSE,
    error_message TEXT
);
"""

CREATE_INDEX_STORE_SQL = """
CREATE INDEX IF NOT EXISTS idx_job_runs_store_id_started_at
ON job_runs(store_id, started_at DESC);
"""

CREATE_INDEX_STATUS_SQL = """
CREATE INDEX IF NOT EXISTS idx_job_runs_status_started_at
ON job_runs(status, started_at DESC);
"""


def main() -> None:
    setup_logging()
    with get_cursor(commit=True) as cursor:
        cursor.execute(CREATE_JOB_RUNS_TABLE_SQL)
        cursor.execute(CREATE_INDEX_STORE_SQL)
        cursor.execute(CREATE_INDEX_STATUS_SQL)
    logger.info("Monitoring schema initialized.")


if __name__ == "__main__":
    main()
