"""SMTP email delivery for Eagle Eye transactional notifications.

SMTP credentials are loaded from the local .env file. Never commit real credentials.
"""
import logging
import smtplib
from email.message import EmailMessage

from backend.config import get_settings

logger = logging.getLogger(__name__)


def send_email(to_email: str, subject: str, body: str, sender_profile: str = "admin") -> bool:
    """Send one email through the selected configured SMTP profile.

    sender_profile may be "admin" or "analyst". Returns False if the selected
    profile is not configured or delivery fails.
    """
    settings = get_settings()
    if sender_profile == "analyst":
        username = settings.smtp_analyst_username
        password = settings.smtp_analyst_password
        from_email = settings.smtp_analyst_from_email
    else:
        username = settings.smtp_username
        password = settings.smtp_password
        from_email = settings.smtp_from_email

    if not all((settings.smtp_host, username, password, from_email)):
        logger.warning("SMTP profile '%s' is not configured; email to %s was not sent", sender_profile, to_email)
        return False

    message = EmailMessage()
    message["From"] = from_email
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
            server.ehlo()
            if settings.smtp_use_tls:
                server.starttls()
                server.ehlo()
            server.login(username, password)
            server.send_message(message)
        return True
    except (OSError, smtplib.SMTPException):
        logger.exception("SMTP delivery failed using profile '%s' for recipient %s", sender_profile, to_email)
        return False
