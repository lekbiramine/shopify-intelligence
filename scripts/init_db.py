from pathlib import Path
from db.connection import get_connection
from config.logging_config import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)

SCHEMA_PATH = Path(__file__).parent.parent / "db" / "schema.sql"


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