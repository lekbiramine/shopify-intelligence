import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool
from contextlib import contextmanager
from config import settings
from config.logging_config import get_logger

logger = get_logger(__name__)

_POOL: ThreadedConnectionPool | None = None


def _get_pool() -> ThreadedConnectionPool:
    global _POOL
    if _POOL is None:
        _POOL = ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            dbname=settings.DB_NAME,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
        )
        logger.info("Database connection pool initialized.")
    return _POOL


def get_connection():
    try:
        pool = _get_pool()
        conn = pool.getconn()
        logger.debug("Database connection established.")
        return conn
    except psycopg2.OperationalError as e:
        logger.error(f"Failed to connect to database: {e}")
        raise


@contextmanager
def get_cursor(commit: bool = False):
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            yield cursor
            if commit:
                conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        try:
            pool = _get_pool()
            pool.putconn(conn)
            logger.debug("Database connection returned to pool.")
        except Exception:
            conn.close()
            logger.debug("Database connection closed.")