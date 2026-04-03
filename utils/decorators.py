import time
import logging
from functools import wraps
from config.logging_config import get_logger

logger = get_logger(__name__)


def retry(attempts: int = 3, delay: float = 2.0, exceptions: tuple = (Exception,)):
    """
    Retries a function on failure.

    :param attempts: number of total attempts
    :param delay: seconds to wait between attempts
    :param exceptions: exception types to catch and retry on
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            for attempt in range(1, attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as e:
                    logger.warning(
                        f"[{fn.__name__}] attempt {attempt}/{attempts} failed: {e}"
                    )
                    if attempt < attempts:
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"[{fn.__name__}] permanently failed after {attempts} attempts."
                        )
                        raise
        return wrapper
    return decorator


def log_execution(fn):
    """
    Logs function entry, exit, and execution time.
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        logger.info(f"[{fn.__name__}] started.")
        start = time.time()
        try:
            result = fn(*args, **kwargs)
            duration = time.time() - start
            logger.info(f"[{fn.__name__}] completed in {duration:.2f}s.")
            return result
        except Exception as e:
            duration = time.time() - start
            logger.error(f"[{fn.__name__}] failed after {duration:.2f}s: {e}")
            raise
    return wrapper