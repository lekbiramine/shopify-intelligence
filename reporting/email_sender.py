import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
from config import settings
from config.logging_config import get_logger

logger = get_logger(__name__)


def build_email(
    subject: str,
    body: str,
    attachment_path: str | None = None,
    recipient: str | None = None,
) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.EMAIL_SENDER
    msg["To"] = recipient or settings.EMAIL_RECIPIENT
    msg.set_content(body)

    if attachment_path:
        file_path = Path(attachment_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Attachment file not found: {attachment_path}")
        msg.add_attachment(
            file_path.read_bytes(),
            maintype="application",
            subtype="pdf",
            filename=file_path.name,
        )
    return msg


def send_email(subject: str, body: str, attachment_path: str | None = None, recipient: str | None = None) -> None:
    """
    Sends a plain text email via SMTP SSL on port 465.
    """
    to_addr = recipient or settings.EMAIL_RECIPIENT
    logger.info(f"Sending email to {to_addr}...")
    settings.validate_email_env()

    msg = build_email(subject, body, attachment_path=attachment_path, recipient=to_addr)
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