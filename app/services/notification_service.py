import logging
import smtplib
from email.message import EmailMessage

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.enums import NotificationChannel, NotificationStatus
from app.models import Notification, User


logger = logging.getLogger("medivault.notifications")


def create_notification(db: Session, user_id: str, title: str, message: str, *, resource_type: str | None = None, resource_id: str | None = None) -> Notification:
    notification = Notification(user_id=user_id, title=title, message=message, related_resource_type=resource_type, related_resource_id=resource_id)
    db.add(notification)
    return notification


def send_email(to_email: str, title: str, message: str) -> bool:
    if not settings.smtp_host:
        logger.info("Email delivery is disabled; the in-app notification remains available")
        return False
    if not settings.smtp_from:
        logger.error("SMTP_FROM is not configured; email delivery skipped")
        return False
    email = EmailMessage()
    email["Subject"], email["From"], email["To"] = title, settings.smtp_from, to_email
    email.set_content(message)
    try:
        smtp_class = smtplib.SMTP_SSL if settings.smtp_use_ssl else smtplib.SMTP
        with smtp_class(settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds) as smtp:
            if settings.smtp_tls and not settings.smtp_use_ssl:
                smtp.starttls()
            if settings.smtp_user and settings.smtp_password:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(email)
        logger.info("Email notification delivered successfully")
        return True
    except (OSError, smtplib.SMTPException):
        logger.exception("Email delivery failed; the in-app notification remains available")
        return False


def notify_with_email(db: Session, user: User, title: str, message: str, resource_type: str | None = None, resource_id: str | None = None) -> None:
    create_notification(db, user.id, title, message, resource_type=resource_type, resource_id=resource_id)
    send_email(user.email, title, message)
