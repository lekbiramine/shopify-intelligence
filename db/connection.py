import psycopg2
import re
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool
from contextlib import contextmanager
from config import settings
from config.logging_config import get_logger

logger = get_logger(__name__)

_POOL: ThreadedConnectionPool | None = None
_TENANT_TABLES = {"orders", "products", "customers", "inventory", "reports", "tasks", "job_runs", "order_items", "variants"}
_DDL_PREFIXES = ("create ", "alter ", "drop ", "truncate ")


def _normalize_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", (sql or "").strip().lower())


def _assert_tenant_scoped_query(sql: str) -> None:
    normalized = _normalize_sql(sql)
    if not normalized or normalized.startswith(_DDL_PREFIXES):
        return
    touched = [table for table in _TENANT_TABLES if re.search(rf"\b{table}\b", normalized)]
    if touched and "store_id" not in normalized:
        raise RuntimeError(
            f"Tenant-scoped query is missing store_id filter/column (tables={','.join(sorted(touched))})."
        )


class ScopedCursor:
    def __init__(self, inner):
        self._inner = inner

    def execute(self, query, vars=None):
        _assert_tenant_scoped_query(str(query))
        return self._inner.execute(query, vars)

    def executemany(self, query, vars_list):
        _assert_tenant_scoped_query(str(query))
        return self._inner.executemany(query, vars_list)

    def __getattr__(self, name):
        return getattr(self._inner, name)


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
            yield ScopedCursor(cursor)
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