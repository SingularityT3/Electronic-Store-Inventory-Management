"""Outgoing email for password reset links."""

import logging
import smtplib
from email.message import EmailMessage

from app.config import Settings

logger = logging.getLogger(__name__)


def send_reset_email(settings: Settings, to: str, link: str) -> None:
    """Send a reset link. Failures are logged (without the link) and not raised."""
    if not settings.smtp_host:
        logger.warning("SMTP_HOST is not set; password reset email was not sent")
        return
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to
    message["Subject"] = "Reset your ESIMS password"
    message.set_content(
        "A password reset was requested for your ESIMS account.\n\n"
        f"Open this link to choose a new password (valid for "
        f"{settings.password_reset_minutes} minutes, single use):\n\n{link}\n\n"
        "If you did not request this, ignore this email. Your password is unchanged."
    )
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            if settings.smtp_starttls:
                smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException):
        logger.exception("Could not send password reset email")
