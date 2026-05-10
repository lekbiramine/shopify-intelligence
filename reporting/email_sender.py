import smtplib
import ssl
import os
from urllib.parse import urlencode
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from config import settings
from config.logging_config import get_logger
from db.queries import get_store_contact_email_by_id
from reporting.html_report import build_html_report

logger = get_logger(__name__)


def build_email(
    subject: str,
    body: str,
    recipient: str,
    html_body: str | None = None,
) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    # Force a consistent display name across all outbound emails.
    # If EMAIL_FROM already includes a name, we still normalize it to "Perspicor".
    _, addr = parseaddr(settings.EMAIL_FROM or "")
    msg["From"] = formataddr(("Perspicor", addr or (settings.EMAIL_FROM or "")))
    msg["To"] = recipient
    # Explicit charsets so clients reliably pick text/html and render UTF-8.
    msg.set_content(body, subtype="plain", charset="utf-8")
    if html_body:
        msg.add_alternative(html_body, subtype="html", charset="utf-8")
    return msg


def send_email(
    subject: str,
    body: str,
    recipient: str,
    html_body: str | None = None,
) -> None:
    """
    Sends an email via SMTP.

    - Port 465 typically uses implicit TLS (`SMTP_SSL`)
    - Port 587 typically uses STARTTLS (`SMTP` + `starttls()`)
    """
    to_addr = (recipient or "").strip()
    if not to_addr:
        raise EnvironmentError("No recipient provided.")
    logger.info("Sending email to %s...", to_addr)
    settings.validate_email_env()

    msg = build_email(subject, body, html_body=html_body, recipient=to_addr)
    context = ssl.create_default_context()
    smtp_host = str(settings.SMTP_HOST or "").strip()
    smtp_port = int(settings.SMTP_PORT)

    try:
        use_ssl = settings.SMTP_USE_SSL or (settings.SMTP_PORT == 465 and not settings.SMTP_USE_STARTTLS)
        use_starttls = settings.SMTP_USE_STARTTLS or (settings.SMTP_PORT in {587, 25} and not settings.SMTP_USE_SSL)

        if use_ssl:
            with smtplib.SMTP_SSL(
                smtp_host,
                smtp_port,
                context=context,
                timeout=20,
            ) as server:
                server.login(settings.SMTP_USERNAME, settings.EMAIL_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
                server.ehlo()
                if use_starttls:
                    server.starttls(context=context)
                    server.ehlo()
                server.login(settings.SMTP_USERNAME, settings.EMAIL_PASSWORD)
                server.send_message(msg)
        logger.info(
            "Email sent successfully.",
            extra={"recipient": to_addr, "smtp_host": smtp_host, "smtp_port": smtp_port},
        )

    except smtplib.SMTPAuthenticationError:
        logger.exception(
            "SMTP authentication failed for recipient=%s via %s:%s",
            to_addr,
            smtp_host,
            smtp_port,
        )
        raise
    except smtplib.SMTPException:
        logger.exception(
            "SMTP error for recipient=%s via %s:%s",
            to_addr,
            smtp_host,
            smtp_port,
        )
        raise
    except Exception:
        logger.exception(
            "Unexpected error sending email for recipient=%s via %s:%s",
            to_addr,
            smtp_host,
            smtp_port,
        )
        raise


def _format_subject_money(value: float | int | None) -> str:
    try:
        amount = float(value or 0.0)
    except (TypeError, ValueError):
        amount = 0.0
    text = f"{amount:,.2f}"
    return text[:-3] if text.endswith(".00") else text


def _build_authoritative_subject(*, actions_count: int, daily_impact: float | int | None) -> str:
    """
    Direct, serious, and authoritative. No emojis, no brackets, no store names.
    """
    n = max(int(actions_count or 0), 0)
    daily = abs(float(daily_impact or 0.0))
    daily_txt = _format_subject_money(daily)
    if n == 1:
        return f"${daily_txt} lost today. 1 action required."
    if n > 1:
        return f"${daily_txt} lost today. {n} actions required."
    return f"You're losing ${daily_txt} today. Here's what to do."


def send_store_report_email(*, store_id: int, report_data: dict) -> str:
    recipient = get_store_contact_email_by_id(store_id)
    if not recipient:
        raise RuntimeError(f"No contact_email configured for store_id={store_id}")
    actions = list(report_data.get("actions") or [])
    subject = _build_authoritative_subject(actions_count=len(actions), daily_impact=report_data.get("daily_impact"))
    base_url = os.getenv("SHOPIFY_APP_BASE_URL", "").strip().rstrip("/")
    unsubscribe_url = None
    if base_url and recipient:
        unsubscribe_url = f"{base_url}/unsubscribe?{urlencode({'email': recipient})}"
    html_content = build_html_report(report_data, unsubscribe_url=unsubscribe_url)
    store_label = str(report_data.get("store_name") or f"Store {store_id}")
    plain_lines = [
        f"{store_label} daily report",
        f"Date: {report_data.get('date') or ''}",
        f"Status: {report_data.get('status') or ''}",
        f"Daily impact: ${_format_subject_money(report_data.get('daily_impact'))}",
        f"Actions: {len(actions)}",
        f"Total value: ${_format_subject_money(report_data.get('total_value'))}",
        "",
    ]
    for i, action in enumerate(actions[:25], start=1):
        label = str(action.get("type") or action.get("action_type") or "Action").strip() or "Action"
        plain_lines.append(f"{i}. {label}")
    if len(actions) > 25:
        plain_lines.append(f"... and {len(actions) - 25} more.")
    plain_body = "\n".join(plain_lines)
    send_email(subject, plain_body, html_body=html_content, recipient=recipient)
    logger.info(
        "Store-scoped email sent",
        extra={"store_id": store_id, "recipient": recipient},
    )
    return recipient
