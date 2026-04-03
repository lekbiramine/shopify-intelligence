from datetime import datetime, timezone
from config.logging_config import get_logger

logger = get_logger(__name__)


def get_email_subject() -> str:
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")
    return f"Store Intelligence Report — {today}"


def wrap_email_body(report_body: str) -> str:
    """
    Wraps the plain text report in a clean email template.
    """
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")

    header = (
        f"Daily Store Intelligence Report\n"
        f"Generated: {today} (UTC)\n"
        f"{'=' * 50}\n"
        "This report was generated automatically by your Shopify automation pipeline.\n"
        f"{'=' * 50}"
    )

    footer = (
        f"{'=' * 50}\n"
        "This is an automated report. Do not reply to this email.\n"
        "For support, contact your automation engineer.\n"
        f"{'=' * 50}"
    )

    return f"{header}\n\n{report_body}\n\n{footer}"