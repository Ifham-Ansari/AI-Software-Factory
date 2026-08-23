"""Email delivery."""

from factory_core.infrastructure.email.messages import EmailMessage, verification_email
from factory_core.infrastructure.email.senders import (
    ConsoleEmailSender,
    EmailSender,
    SmtpEmailSender,
    build_email_sender,
)

__all__ = [
    "ConsoleEmailSender",
    "EmailMessage",
    "EmailSender",
    "SmtpEmailSender",
    "build_email_sender",
    "verification_email",
]
