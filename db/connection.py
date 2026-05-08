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


class DatabaseConnectionError(RuntimeError):
    """Raised when acquiring a DB connection fails."""


class DatabaseQueryError(RuntimeError):
    """Raised when executing a DB query fails."""


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
        settings.validate_db_env()
        _POOL = ThreadedConnectionPool(
            minconn=settings.DB_POOL_MIN,
            maxconn=settings.DB_POOL_MAX,
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            dbname=settings.DB_NAME,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            sslmode=settings.DB_SSLMODE,
            connect_timeout=10,
            application_name="perspicor",
        )
        logger.info(
            "Database connection pool initialized.",
            extra={
                "db_host": settings.DB_HOST,
                "db_port": settings.DB_PORT,
                "db_name": settings.DB_NAME,
                "db_sslmode": settings.DB_SSLMODE,
                "db_pool_min": settings.DB_POOL_MIN,
                "db_pool_max": settings.DB_POOL_MAX,
            },
        )
    return _POOL


def get_connection():
    try:
        pool = _get_pool()
        conn = pool.getconn()
        logger.debug("Database connection established.")
        return conn
    except psycopg2.OperationalError as e:
        logger.exception("Failed to connect to database.")
        raise DatabaseConnectionError("Database connection failed.") from e


def return_connection(conn, *, close: bool = False) -> None:
    if conn is None:
        return
    try:
        pool = _get_pool()
        pool.putconn(conn, close=close)
        logger.debug("Database connection returned to pool.")
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        logger.debug("Database connection closed.")


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
        logger.exception("Database query failed.")
        raise DatabaseQueryError("Database operation failed.") from e
    finally:
        return_connection(conn)