import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path("logs")
APP_LOG = LOG_DIR / "app.log"
ERROR_LOG = LOG_DIR / "errors.log"

LOG_DIR.mkdir(parents=True, exist_ok=True)

_logging_initialized = False


def setup_logging():
    global _logging_initialized
    if _logging_initialized:
        return
    _logging_initialized = True

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # App handler — all levels
    app_handler = RotatingFileHandler(
        APP_LOG, maxBytes=5 * 1024 * 1024, backupCount=3 # 5mb
    )
    app_handler.setLevel(logging.DEBUG)
    app_handler.setFormatter(formatter)

    # Error handler — errors only
    error_handler = RotatingFileHandler(
        ERROR_LOG, maxBytes=5 * 1024 * 1024, backupCount=3
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(app_handler)
    root_logger.addHandler(error_handler)
    root_logger.addHandler(console_handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)