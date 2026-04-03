from scheduler.run_pipeline import run_etl, run_reporting, run_pipeline
from config.logging_config import get_logger

logger = get_logger(__name__)


def task_etl_only() -> None:
    """
    Runs only the ETL pipeline — extract, transform, load.
    Useful for syncing data without sending a report.
    """
    logger.info("Task: ETL only.")
    run_etl()


def task_reporting_only() -> None:
    """
    Runs only the reporting pipeline — analytics, format, email.
    Useful when data is already synced and you just need a report.
    """
    logger.info("Task: Reporting only.")
    run_reporting()


def task_full_pipeline() -> None:
    """
    Runs the full pipeline — ETL + reporting.
    This is the default daily task.
    """
    logger.info("Task: Full pipeline.")
    run_pipeline()