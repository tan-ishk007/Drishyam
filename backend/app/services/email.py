"""Transactional email abstraction with a development-only secure mailbox recorder."""

from __future__ import annotations

import json
import logging
import smtplib
import ssl
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from uuid import uuid4

from app.core.config import get_settings
from app.services.gmail_api import GmailApiConfigurationError, GmailApiDeliveryError, send_message as send_gmail_api_message

logger = logging.getLogger(__name__)
settings = get_settings()


class TransactionalEmailProvider(ABC):
    @abstractmethod
    def send_otp(self, recipient: str, code: str, *, purpose: str) -> None:
        raise NotImplementedError


class DevelopmentMailboxProvider(TransactionalEmailProvider):
    """Writes OTPs only to an explicitly enabled local mailbox; never logs them."""

    def send_otp(self, recipient: str, code: str, *, purpose: str) -> None:
        if not settings.allow_local_console_email:
            raise RuntimeError("Local console mailbox is disabled; set ALLOW_LOCAL_CONSOLE_EMAIL=true only for a localhost test runtime")
        mailbox = settings.storage_root.parent / "dev_mailbox"
        mailbox.mkdir(parents=True, exist_ok=True)
        payload = {
            "to": recipient,
            "subject": "Your DRISHYAM verification code" if purpose == "signup_verification" else "Your DRISHYAM sign-in code",
            "verification_code": code,
            "purpose": purpose,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        (mailbox / f"verification-{uuid4()}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.info("Development verification message recorded for a local mailbox")


class GmailSmtpProvider(TransactionalEmailProvider):
    """Prototype Gmail SMTP sender authenticated with a Google App Password only."""

    def send_otp(self, recipient: str, code: str, *, purpose: str) -> None:
        sender = settings.gmail_smtp_email.strip() if settings.gmail_smtp_email else ""
        app_password = settings.gmail_app_password.get_secret_value().replace(" ", "") if settings.gmail_app_password else ""
        if not sender or not app_password:
            raise RuntimeError("GMAIL_SMTP_EMAIL and GMAIL_APP_PASSWORD are required when EMAIL_PROVIDER=gmail_smtp")
        subject = "Verify your DRISHYAM account" if purpose == "signup_verification" else "Your DRISHYAM sign-in code"
        message = EmailMessage()
        message["From"] = f"DRISHYAM Security <{sender}>"
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(f"Your one-time DRISHYAM code is: {code}\n\nIt expires shortly. If you did not request it, you can ignore this email.")
        try:
            try:
                with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=15) as smtp:
                    smtp.login(sender, app_password)
                    smtp.send_message(message)
            except OSError as ssl_error:
                logger.warning("Gmail SMTP implicit-TLS connection unavailable: error_class=%s; attempting STARTTLS fallback", type(ssl_error).__name__)
                with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as smtp:
                    smtp.ehlo()
                    smtp.starttls(context=ssl.create_default_context())
                    smtp.ehlo()
                    smtp.login(sender, app_password)
                    smtp.send_message(message)
        except smtplib.SMTPAuthenticationError as exc:
            logger.warning("Gmail SMTP OTP authentication rejected: error_class=%s smtp_status=%s", type(exc).__name__, exc.smtp_code)
            raise RuntimeError("Gmail SMTP authentication failed") from exc
        except smtplib.SMTPException as exc:
            logger.warning("Gmail SMTP OTP delivery rejected: error_class=%s smtp_status=%s", type(exc).__name__, getattr(exc, "smtp_code", "n/a"))
            raise RuntimeError("Gmail SMTP rejected OTP delivery") from exc
        except OSError as exc:
            logger.warning("Gmail SMTP OTP connection failure: error_class=%s", type(exc).__name__)
            raise RuntimeError("Gmail SMTP connection failed") from exc
        logger.info("Gmail SMTP accepted a transactional OTP message")


class GmailApiProvider(TransactionalEmailProvider):
    """HTTPS Gmail API sender; refresh credentials stay in a protected local Docker volume."""

    def send_otp(self, recipient: str, code: str, *, purpose: str) -> None:
        sender = settings.gmail_api_sender.strip() if settings.gmail_api_sender else ""
        if not sender:
            raise RuntimeError("GMAIL_API_SENDER is required when EMAIL_PROVIDER=gmail_api")
        subject = "Verify your DRISHYAM account" if purpose == "signup_verification" else "Your DRISHYAM sign-in code"
        message = EmailMessage()
        message["From"] = f"DRISHYAM Security <{sender}>"
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(f"Your one-time DRISHYAM code is: {code}\n\nIt expires shortly. If you did not request it, you can ignore this email.")
        try:
            send_gmail_api_message(message)
        except (GmailApiConfigurationError, GmailApiDeliveryError) as exc:
            raise RuntimeError("Gmail API OTP delivery is unavailable") from exc


def get_email_provider() -> TransactionalEmailProvider:
    provider = settings.email_provider.lower().strip()
    if provider == "console":
        return DevelopmentMailboxProvider()
    if provider == "gmail_smtp":
        return GmailSmtpProvider()
    if provider == "gmail_api":
        return GmailApiProvider()
    raise RuntimeError(f"Unsupported EMAIL_PROVIDER: {provider}")
