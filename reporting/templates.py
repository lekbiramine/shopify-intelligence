from datetime import datetime, timezone
from config.logging_config import get_logger

logger = get_logger(__name__)


def get_email_subject() -> str:
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")
    return f"Store Intelligence Report — {today}"


def get_action_email_subject(top_action_daily_loss: float) -> str:
    return f"Today: Fix 1 issue losing ${float(top_action_daily_loss):,.2f}/day"


def build_action_email_body(*, daily_loss: float, top_action: dict, dashboard_url: str) -> str:
    action_title = str(top_action.get("title") or "").strip()
    context = str(top_action.get("context") or "").strip()
    why = context[:180].strip() or "Measured issue requires immediate execution."
    expected_result = (top_action.get("expected_result") or {})
    target_min = expected_result.get("target_min", 0)
    target_max = expected_result.get("target_max", 0)
    lines = [
        f"You're currently losing ${float(daily_loss):,.2f}/day from 1 critical issue.",
        "",
        f"Action #1: {action_title}",
        "",
        why,
        "",
        f"Target: +{int(target_min)}-{int(target_max)} orders in 7 days",
        "",
        f"View full action plan -> {dashboard_url}",
    ]
    return "\n".join(lines)


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