import smtplib
import ssl
from email.message import EmailMessage
from config import settings
from config.logging_config import get_logger
from db.queries import get_store_contact_email_by_id
from reporting.html_report import build_html_report

logger = get_logger(__name__)


def build_email(
    subject: str,
    body: str,
    html_body: str | None = None,
    recipient: str | None = None,
) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.EMAIL_SENDER
    msg["To"] = recipient or settings.EMAIL_RECIPIENT
    msg.set_content(body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")
    return msg


def send_email(subject: str, body: str, html_body: str | None = None, recipient: str | None = None) -> None:
    """
    Sends a plain text email via SMTP SSL on port 465.
    """
    to_addr = recipient or settings.EMAIL_RECIPIENT
    logger.info(f"Sending email to {to_addr}...")
    settings.validate_email_env()

    msg = build_email(subject, body, html_body=html_body, recipient=to_addr)
    context = ssl.create_default_context()

    try:
        with smtplib.SMTP_SSL(
            settings.SMTP_HOST,
            settings.SMTP_PORT,
            context=context,
        ) as server:
            server.login(settings.EMAIL_SENDER, settings.EMAIL_PASSWORD)
            server.send_message(msg)
        logger.info("Email sent successfully.")

    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"SMTP authentication failed: {e}")
        raise
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error occurred: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error sending email: {e}")
        raise


def _format_subject_money(value: float | int | None) -> str:
    try:
        amount = float(value or 0.0)
    except (TypeError, ValueError):
        amount = 0.0
    text = f"{amount:,.2f}"
    return text[:-3] if text.endswith(".00") else text


def send_store_report_email(*, store_id: int, report_data: dict) -> str:
    recipient = get_store_contact_email_by_id(store_id)
    if not recipient:
        raise RuntimeError(f"No contact_email configured for store_id={store_id}")
    actions = list(report_data.get("actions") or [])
    subject = (
        f"⚡ {str(report_data.get('store_name') or f'Store {store_id}')} — "
        f"{len(actions)} actions worth ${_format_subject_money(report_data.get('total_value'))} today"
    )
    html_content = build_html_report(report_data)
    plain_body = (
        f"{report_data.get('store_name') or f'Store {store_id}'} intelligence report\n"
        f"Date: {report_data.get('date') or ''}\n"
        f"Actions: {len(actions)}\n"
        f"Total value: ${_format_subject_money(report_data.get('total_value'))}\n"
    )
    send_email(subject, plain_body, html_body=html_content, recipient=recipient)
    logger.info(
        "Store-scoped email sent",
        extra={"store_id": store_id, "recipient": recipient},
    )
    return recipient
