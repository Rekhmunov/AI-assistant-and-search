"""Отправка email-оповещений администраторам через SMTP."""

from __future__ import annotations

import email.message
import logging

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


def _parse_emails(raw: str) -> list[str]:
    return [e.strip() for e in raw.replace(";", ",").split(",") if e.strip()]


async def send_admin_alert(
    subject: str,
    body: str,
    *,
    settings: Settings | None = None,
) -> bool:
    """
    Отправляет email всем адресам из ALERT_EMAILS.
    Возвращает True если хотя бы одно письмо отправлено успешно.
    """
    settings = settings or get_settings()
    if not settings.smtp_configured:
        return False

    recipients = _parse_emails(settings.alert_emails)
    if not recipients:
        return False

    from_addr = settings.smtp_from.strip() or settings.smtp_user.strip()

    msg = email.message.EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(recipients)
    msg.set_content(body)

    try:
        import aiosmtplib
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host.strip(),
            port=settings.smtp_port,
            username=settings.smtp_user.strip(),
            password=settings.smtp_password.strip(),
            start_tls=settings.smtp_use_tls,
        )
        logger.info("Admin alert sent to %s: %s", recipients, subject)
        return True
    except Exception as exc:
        logger.warning("Admin alert email failed: %s", exc)
        return False
