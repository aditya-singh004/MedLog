import logging

from app.core.config import settings
from app.services import notification_service


def test_disabled_email_does_not_log_sensitive_content(monkeypatch, caplog):
    monkeypatch.setattr(settings, "smtp_host", None)
    caplog.set_level(logging.INFO)

    delivered = notification_service.send_email(
        "private.patient@example.com",
        "Prescription Added",
        "Sensitive medical notification content",
    )

    assert delivered is False
    assert "private.patient@example.com" not in caplog.text
    assert "Sensitive medical notification content" not in caplog.text


def test_smtp_failure_falls_back_without_raising(monkeypatch, caplog):
    class FailingSMTP:
        def __init__(self, *args, **kwargs):
            raise OSError("provider unavailable")

    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_from", "noreply@example.com")
    monkeypatch.setattr(settings, "smtp_use_ssl", False)
    monkeypatch.setattr(notification_service.smtplib, "SMTP", FailingSMTP)
    caplog.set_level(logging.ERROR)

    delivered = notification_service.send_email(
        "private.patient@example.com",
        "Consent Approved",
        "Sensitive consent content",
    )

    assert delivered is False
    assert "private.patient@example.com" not in caplog.text
    assert "Sensitive consent content" not in caplog.text


def test_smtp_success(monkeypatch):
    state = {"sent": False, "started_tls": False, "logged_in": False}

    class SuccessfulSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self):
            state["started_tls"] = True

        def login(self, username, password):
            state["logged_in"] = bool(username and password)

        def send_message(self, message):
            state["sent"] = True

    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_from", "noreply@example.com")
    monkeypatch.setattr(settings, "smtp_user", "smtp-user")
    monkeypatch.setattr(settings, "smtp_password", "smtp-password")
    monkeypatch.setattr(settings, "smtp_tls", True)
    monkeypatch.setattr(settings, "smtp_use_ssl", False)
    monkeypatch.setattr(notification_service.smtplib, "SMTP", SuccessfulSMTP)

    assert notification_service.send_email("patient@example.com", "Appointment Scheduled", "Your appointment is confirmed") is True
    assert state == {"sent": True, "started_tls": True, "logged_in": True}
