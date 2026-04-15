from pathlib import Path
import sys

# Ensure repo root is importable when running as a script
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from db.connection import get_connection
from config.logging_config import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)

SCHEMA_PATH = REPO_ROOT / "db" / "schema.sql"


def init_db() -> None:
    logger.info("Initializing database schema...")

    sql = SCHEMA_PATH.read_text()

    try:
        conn = get_connection()
        conn.autocommit = True
        with conn.cursor() as cursor:
            cursor.execute(sql)
        conn.close()
        logger.info("Database schema created successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


if __name__ == "__main__":
    init_db()