"""Domain value objects.

Value objects normalise and validate at construction, so an invalid value cannot exist
anywhere downstream. A function taking an ``Email`` never has to wonder whether it was
trimmed, lowercased, or checked.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Annotated, Any

from pydantic import BeforeValidator, EmailStr, Field, TypeAdapter

MAX_EMAIL_LENGTH = 254
MAX_PROJECT_NAME_LENGTH = 120
MAX_PROJECT_SLUG_LENGTH = 80
MAX_DESCRIPTION_LENGTH = 2000


def _normalise_email(value: Any) -> Any:
    """Trim and lowercase an email before validation.

    Addresses are compared for uniqueness, so ``Ada@Example.com`` and
    ``ada@example.com`` must not be able to register as two separate accounts.
    """
    if isinstance(value, str):
        return value.strip().lower()
    return value


Email = Annotated[EmailStr, BeforeValidator(_normalise_email)]

ProjectName = Annotated[str, Field(min_length=1, max_length=MAX_PROJECT_NAME_LENGTH)]
ProjectDescription = Annotated[str, Field(max_length=MAX_DESCRIPTION_LENGTH)]
Password = Annotated[str, Field(min_length=8, max_length=128)]

_email_adapter: TypeAdapter[str] = TypeAdapter(Email)

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")
_SLUG_TRIM = re.compile(r"^-+|-+$")


def normalise_email(value: str) -> str:
    """Validate and normalise an email address.

    Raises:
        pydantic.ValidationError: The address is not a valid email.
    """
    return _email_adapter.validate_python(value)


def slugify(value: str) -> str:
    """Derive a URL-safe slug from a display name.

    Unicode is folded to ASCII so that visually distinct names cannot produce identical
    slugs by accident, and an empty result falls back to ``project`` rather than
    returning an empty string that would break a URL.
    """
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    slug = _SLUG_STRIP.sub("-", ascii_only.lower())
    slug = _SLUG_TRIM.sub("", slug)[:MAX_PROJECT_SLUG_LENGTH]
    slug = _SLUG_TRIM.sub("", slug)
    return slug or "project"
