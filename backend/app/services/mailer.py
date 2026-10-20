"""Outgoing email. Backends: smtp (prod, Mailpit in compose), console (dev log), memory (tests).

Sending never fails the request that triggered it: errors are logged without the address.
"""

import asyncio
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

import structlog

from app.config import get_settings

log = structlog.get_logger()


@dataclass(frozen=True)
class Mail:
    to: str
    subject: str
    body: str


outbox: list[Mail] = []  # memory backend


def _send_smtp(mail: Mail) -> None:
    settings = get_settings()
    message = EmailMessage()
    message["From"] = settings.mail_from
    message["To"] = mail.to
    message["Subject"] = mail.subject
    message.set_content(mail.body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        if settings.smtp_starttls:
            smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password.get_secret_value())
        smtp.send_message(message)


async def send_mail(mail: Mail) -> None:
    backend = get_settings().mail_backend
    try:
        if backend == "memory":
            outbox.append(mail)
        elif backend == "console":
            # Development only: the body holds a one-time link, so it stays out of prod logs.
            log.info("mail_console", subject=mail.subject, body=mail.body)
        else:
            await asyncio.to_thread(_send_smtp, mail)
            log.info("mail_sent", subject=mail.subject)
    except Exception:
        log.exception("mail_failed", subject=mail.subject)
