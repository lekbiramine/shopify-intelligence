import smtplib
import ssl
from email.message import EmailMessage
from config import settings
from config.logging_config import get_logger

logger = get_logger(__name__)


def build_email(subject: str, body: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.EMAIL_SENDER
    msg["To"] = settings.EMAIL_RECIPIENT
    msg.set_content(body)
    return msg


def send_email(subject: str, body: str) -> None:
    """
    Sends a plain text email via SMTP SSL on port 465.
    """
    logger.info(f"Sending email to {settings.EMAIL_RECIPIENT}...")

    msg = build_email(subject, body)
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