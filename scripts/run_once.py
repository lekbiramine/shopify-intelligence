import argparse

from config.logging_config import get_logger, setup_logging

setup_logging()
from scheduler.tasks import task_etl_only, task_reporting_only, task_full_pipeline

logger = get_logger(__name__)

TASKS = {
    "etl": task_etl_only,
    "report": task_reporting_only,
    "full": task_full_pipeline,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Shopify automation pipeline manually once.",
    )
    parser.add_argument(
        "--task",
        choices=TASKS.keys(),
        default="full",
        help="Task to run: 'etl', 'report', or 'full' (default: full)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    task_fn = TASKS[args.task]
    logger.info(f"Running task manually: {args.task}")
    task_fn()


if __name__ == "__main__":
    main()