"""Email transports.

``EmailSender`` is a Protocol, so an adapter satisfies it by shape and never imports from
here. Two implementations ship:

* :class:`ConsoleEmailSender` writes the message to the log. It exists so the whole
  signup flow works with no SMTP credentials — but it prints a one-time code, so
  configuration refuses to start production with it selected.
* :class:`SmtpEmailSender` sends real mail.

Sending is I/O and can fail. Neither implementation swallows that: a caller decides
whether a delivery failure should fail the request or be retried, because the right answer
differs between "verify your email" and a marketing send.
"""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage as MimeMessage
from typing import Protocol, runtime_checkable

from factory_core.config.email import EmailSettings
from factory_core.errors import ServiceUnavailableError
from factory_core.infrastructure.email.messages import EmailMessage
from factory_core.observability import get_logger

logger = get_logger(__name__)


@runtime_checkable
class EmailSender(Protocol):
    """Delivers a message."""

    async def send(self, message: EmailMessage) -> None:
        """Send a message.

        Raises:
            ServiceUnavailableError: Delivery failed.
        """
        ...


class ConsoleEmailSender:
    """Writes messages to the log instead of sending them.

    **Development only.** The body of a verification email contains a live one-time code,
    so this transport puts a credential into the log stream. That is an acceptable trade
    on a developer machine, where the alternative is being unable to sign up at all, and
    unacceptable anywhere else — which is why ``Settings`` refuses to start production
    with ``EMAIL__TRANSPORT=console``.
    """

    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> None:
        """Record the message and log it."""
        self.sent.append(message)
        # Logged as a single pre-formatted block rather than structured fields: the point
        # is for a developer to read the code out of their terminal.
        logger.warning(
            "email.console_transport",
            to=message.to,
            subject=message.subject,
            body=f"\n{'-' * 60}\n{message.text_body}{'-' * 60}",
        )


class SmtpEmailSender:
    """Sends mail over SMTP.

    ``smtplib`` is synchronous, so each send runs in a worker thread. A blocking socket
    call on the event loop would stall every other request on the process for the duration
    of the handshake.
    """

    def __init__(self, settings: EmailSettings) -> None:
        if settings.smtp_host is None:
            msg = "SmtpEmailSender requires EMAIL__SMTP_HOST"
            raise ValueError(msg)
        self._settings = settings
        self._host = settings.smtp_host

    async def send(self, message: EmailMessage) -> None:
        """Send a message.

        Raises:
            ServiceUnavailableError: The message could not be delivered.
        """
        try:
            await asyncio.to_thread(self._send_blocking, message)
        except (smtplib.SMTPException, OSError) as exc:
            # The exception type is logged; its message is not, because SMTP errors can
            # echo the credentials used to authenticate.
            logger.warning("email.send_failed", to=message.to, error=type(exc).__name__)
            raise ServiceUnavailableError("The verification email could not be sent.") from exc

    def _send_blocking(self, message: EmailMessage) -> None:
        """Build and deliver the MIME message. Runs off the event loop."""
        settings = self._settings
        mime = MimeMessage()
        mime["Subject"] = message.subject
        mime["From"] = f"{settings.from_name} <{settings.from_address}>"
        mime["To"] = message.to
        mime.set_content(message.text_body)
        mime.add_alternative(message.html_body, subtype="html")

        with smtplib.SMTP(
            self._host, settings.smtp_port, timeout=settings.smtp_timeout_seconds
        ) as client:
            if settings.smtp_use_tls:
                client.starttls()
            if settings.smtp_username and settings.smtp_password:
                client.login(
                    settings.smtp_username, settings.smtp_password.get_secret_value()
                )
            client.send_message(mime)


def build_email_sender(settings: EmailSettings) -> EmailSender:
    """Select a transport from configuration."""
    if settings.transport == "smtp":
        return SmtpEmailSender(settings)
    return ConsoleEmailSender()
