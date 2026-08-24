"""Email message construction.

Templates live here as plain functions rather than a templating engine: there are two
messages, both short, and a template engine would be a dependency plus a file-loading
story for no benefit. Revisit when there are ten.

Both a plain-text and an HTML part are produced. Plain text is not a fallback nicety — a
verification mail that renders as a blank page in a text-only client is a support ticket,
and some corporate gateways strip HTML entirely.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EmailMessage:
    """A message ready to hand to a transport."""

    to: str
    subject: str
    text_body: str
    html_body: str


def extract_code(text_body: str, *, length: int = 6) -> str | None:
    """Pull a bare numeric code out of a message body, or ``None`` if none is present.

    One implementation shared by the test double and the test-environment debug endpoint,
    so both agree on where a code can appear — the verification service itself never
    returns or logs one.
    """
    match = re.search(rf"\b(\d{{{length}}})\b", text_body)
    return match.group(1) if match else None


def _escape(value: str) -> str:
    """Escape a value for interpolation into HTML.

    A display name comes from user input and lands in an email body. Without escaping,
    a name containing markup would be rendered by the recipient's client.
    """
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def verification_email(
    *, to: str, display_name: str, code: str, expires_in_minutes: int
) -> EmailMessage:
    """Build the message carrying a one-time verification code."""
    name = _escape(display_name)
    safe_code = _escape(code)

    text_body = (
        f"Hi {display_name},\n\n"
        f"Your verification code is: {code}\n\n"
        f"It expires in {expires_in_minutes} minutes and can be used once.\n\n"
        "If you did not create an account, you can ignore this message — "
        "no account is active until this code is used.\n\n"
        "— AI Software Factory\n"
    )

    # Deliberately simple markup with inline styles. Email clients support a small and
    # inconsistent subset of CSS; anything more elaborate breaks somewhere.
    html_body = f"""\
<!doctype html>
<html>
  <body style="margin:0;padding:24px;background:#f4f5f7;font-family:system-ui,-apple-system,'Segoe UI',sans-serif;color:#1a2030;">
    <div style="max-width:480px;margin:0 auto;background:#ffffff;border-radius:12px;padding:32px;">
      <h1 style="margin:0 0 8px;font-size:20px;">Verify your email</h1>
      <p style="margin:0 0 24px;color:#5b6478;font-size:14px;">Hi {name}, use this code to finish setting up your account.</p>
      <div style="font-family:ui-monospace,Menlo,Consolas,monospace;font-size:32px;font-weight:700;letter-spacing:8px;text-align:center;padding:20px;background:#f4f5f7;border-radius:8px;color:#1a2030;">{safe_code}</div>
      <p style="margin:24px 0 0;color:#5b6478;font-size:13px;">Expires in {expires_in_minutes} minutes. It can be used once.</p>
      <p style="margin:16px 0 0;color:#8a93a6;font-size:12px;">If you did not create an account, ignore this message. No account is active until this code is used.</p>
    </div>
  </body>
</html>
"""
    return EmailMessage(
        to=to,
        subject=f"{code} is your verification code",
        text_body=text_body,
        html_body=html_body,
    )
