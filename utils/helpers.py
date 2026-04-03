from datetime import datetime, timezone
from config.logging_config import get_logger

logger = get_logger(__name__)


def utc_now() -> datetime:
    """Returns current UTC datetime."""
    return datetime.now(timezone.utc)


def parse_datetime(value: str | None) -> datetime | None:
    """
    Parses an ISO 8601 datetime string into a timezone-aware datetime object.
    Returns None if value is None or unparseable.
    """
    if not value:
        return None
    try:
        value = value.replace("Z", "+00:00")
        return datetime.fromisoformat(value)
    except (ValueError, TypeError) as e:
        logger.warning(f"Failed to parse datetime '{value}': {e}")
        return None


def days_since(dt: datetime | None) -> int | None:
    """
    Returns number of days between a given datetime and now.
    Returns None if dt is None.
    """
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = utc_now() - dt
    return delta.days


def safe_float(value, default: float = 0.0) -> float:
    """Safely converts a value to float, returning default on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value, default: int = 0) -> int:
    """Safely converts a value to int, returning default on failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def chunk_list(lst: list, size: int) -> list[list]:
    """Splits a list into chunks of given size."""
    return [lst[i: i + size] for i in range(0, len(lst), size)]