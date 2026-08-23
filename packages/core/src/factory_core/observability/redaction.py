"""Secret redaction for anything leaving the process.

Three independent strategies, because any one of them alone has a blind spot:

1. **Known values.** Secrets loaded from configuration are registered at startup and
   matched literally. This is exact but only covers what we know about.
2. **Sensitive key names.** A mapping key like ``password`` or ``authorization`` has its
   value replaced regardless of content. Catches values we never registered.
3. **Shape patterns.** Recognisable credential formats (JWTs, bearer headers, Postgres
   URLs with a password, common provider key prefixes) are matched anywhere in a string.
   Catches secrets that arrive from outside, such as in a third-party error message.

The redactor is deliberately biased toward over-redaction. A log line that is harder to
read costs a few seconds; a leaked credential costs an incident.
"""

from __future__ import annotations

import re
from typing import Any, Final

REDACTED: Final = "[REDACTED]"

# Values shorter than this are too likely to be ordinary words to match literally.
_MIN_LITERAL_LENGTH: Final = 8

_SENSITIVE_KEY_PARTS: Final[frozenset[str]] = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "access_key",
        "private_key",
        "authorization",
        "auth",
        "cookie",
        "session",
        "credential",
        "jwt",
        "salt",
        "signature",
        "dsn",
        "connection_string",
    }
)

# Key names that contain a sensitive substring but are safe and useful to log.
_SAFE_KEY_ALLOWLIST: Final[frozenset[str]] = frozenset(
    {
        "token_type",
        "token_id",
        "session_id",
        "auth_method",
        "has_password",
        "password_changed_at",
        "token_family_id",
        "expires_in",
    }
)

_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    # JSON Web Tokens
    re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\b"),
    # Authorization header values
    re.compile(r"\b(?:Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE),
    # Credentials embedded in a URL: scheme://user:password@host
    re.compile(r"(?<=://)([^:/\s@]+):([^@/\s]+)(?=@)"),
    # Common provider key shapes
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    # PEM private key blocks
    re.compile(r"-----BEGIN[A-Z ]*PRIVATE KEY-----[\s\S]*?-----END[A-Z ]*PRIVATE KEY-----"),
)


class SecretRedactor:
    """Removes secret material from strings and nested structures.

    A single instance is shared process-wide. Registration happens at startup, before
    any request is served, so the set of known values is stable during operation.
    """

    def __init__(self) -> None:
        self._known: set[str] = set()

    def register(self, *values: str | None) -> None:
        """Register literal secret values to redact on sight.

        A value that looks like a URL with credentials also registers its password
        component on its own. Driver and client errors frequently echo just the password
        rather than the whole connection string, and registering the full URL would not
        match that.

        Values shorter than the minimum length are ignored: matching them literally would
        corrupt unrelated log output without meaningfully protecting anything.
        """
        for value in values:
            if not value:
                continue
            if len(value) >= _MIN_LITERAL_LENGTH:
                self._known.add(value)
            password = url_password(value)
            if password and len(password) >= _MIN_LITERAL_LENGTH:
                self._known.add(password)

    def clear(self) -> None:
        """Forget every registered value. Intended for test isolation."""
        self._known.clear()

    @staticmethod
    def is_sensitive_key(key: str) -> bool:
        """Whether a mapping key's value should be redacted on name alone."""
        lowered = key.lower()
        if lowered in _SAFE_KEY_ALLOWLIST:
            return False
        return any(part in lowered for part in _SENSITIVE_KEY_PARTS)

    def redact_text(self, text: str) -> str:
        """Redact known values and recognisable credential shapes from a string."""
        for known in self._known:
            if known in text:
                text = text.replace(known, REDACTED)
        for pattern in _PATTERNS:
            text = pattern.sub(_replace_match, text)
        return text

    def redact(self, value: Any, *, key: str | None = None) -> Any:
        """Recursively redact a value of any shape.

        Args:
            value: The value to clean. Mappings, sequences, strings and scalars are all
                handled; unknown types are returned unchanged.
            key: The mapping key this value was found under, when applicable. A
                sensitive key redacts its value outright.
        """
        if key is not None and self.is_sensitive_key(key) and value is not None:
            return REDACTED
        if isinstance(value, str):
            return self.redact_text(value)
        if isinstance(value, dict):
            return {k: self.redact(v, key=str(k)) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            cleaned = [self.redact(item) for item in value]
            return type(value)(cleaned) if isinstance(value, (list, tuple)) else set(cleaned)
        return value


def url_password(url: str) -> str | None:
    """Extract the password from a connection URL, if it has one.

    Returns ``None`` for anything that is not a credentialed URL, so it is safe to call on
    every registered value without the caller checking first.
    """
    scheme, separator, remainder = url.partition("://")
    if not separator or "@" not in remainder or " " in scheme:
        return None
    credentials = remainder.split("@", 1)[0]
    if ":" not in credentials:
        return None
    return credentials.split(":", 1)[1] or None


def _replace_match(match: re.Match[str]) -> str:
    """Replace a pattern match, preserving a non-secret prefix where one exists.

    For ``user:password@host`` only the password is secret; keeping the username makes
    the log line far more useful for debugging connection problems.
    """
    if match.re.groups == 2:
        return f"{match.group(1)}:{REDACTED}"
    return REDACTED


_redactor = SecretRedactor()


def get_redactor() -> SecretRedactor:
    """Return the process-wide redactor."""
    return _redactor


def redaction_processor(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """structlog processor that redacts every value in the event.

    Installed last in the processor chain so it sees the fully assembled event,
    including anything added by earlier processors.
    """
    result = _redactor.redact(event_dict)
    return result if isinstance(result, dict) else event_dict
