"""High-entropy credential detection.

The redactor's fourth strategy, kept separate because it is the only one that is a
*heuristic* rather than an exact match, and heuristics need their own tests.

The idea: a credential from a provider we have never integrated with matches no known
pattern and is not a registered value, but it still looks unmistakably unlike prose. A
32-character random token scores around 4.8 bits of Shannon entropy per character;
English sits near 3.0 and a dotted identifier lower still.

Being wrong in either direction has a cost, so the filter is deliberately narrow:

* A false negative leaks a credential.
* A false positive redacts a correlation id and makes an incident untraceable.

Hence the allowlist and the mixed-content requirement below. Both exist because without
them this redacted UUIDs and long snake_case identifiers out of every log line.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from functools import lru_cache
from typing import Final

# Entropy thresholds. A 32-character random token scores about 4.8 bits per character;
# English prose sits near 3.0 and a dotted identifier or file path lower still. 4.0 is
# comfortably above ordinary text while below anything randomly generated.
_MIN_ENTROPY_LENGTH: Final = 24
_ENTROPY_THRESHOLD: Final = 4.0

# Long high-entropy strings that are routine and safe to log. Without this, a hex digest
# used as a correlation id would be redacted and make traces unfollowable.
_ENTROPY_ALLOWLIST: Final[tuple[re.Pattern[str], ...]] = (
    # UUIDs, with or without hyphens - request ids, entity ids.
    re.compile(
        r"^[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}$"
    ),
    # ISO-8601 timestamps.
    re.compile(r"^\d{4}-\d{2}-\d{2}T[\d:.+-]+Z?$"),
)


def shannon_entropy(text: str) -> float:
    """Bits of entropy per character.

    Shannon entropy over the character distribution. It cannot tell a secret from a
    random-looking identifier, which is why the allowlist above exists - the measure is
    a heuristic backstop, not a classifier.
    """
    if not text:
        return 0.0
    counts = Counter(text)
    length = len(text)
    return -sum((n / length) * math.log2(n / length) for n in counts.values())


def _score(token: str) -> bool:
    """Inner check, split out so the public wrapper carries the docstring."""
    if len(token) < _MIN_ENTROPY_LENGTH:
        return False
    if any(pattern.match(token) for pattern in _ENTROPY_ALLOWLIST):
        return False
    # A token with no digits is almost always prose or an identifier path; requiring
    # mixed content sharply reduces false positives on long English words joined by
    # underscores, which are common in this codebase's own log messages.
    has_digit = any(c.isdigit() for c in token)
    has_alpha = any(c.isalpha() for c in token)
    if not (has_digit and has_alpha):
        return False
    return shannon_entropy(token) >= _ENTROPY_THRESHOLD


@lru_cache(maxsize=1)
def token_pattern() -> re.Pattern[str]:
    """The compiled candidate-token pattern.

    Cached rather than module-level so the threshold constants above stay the single
    place the length is expressed.
    """
    return re.compile(rf"[A-Za-z0-9+/_-]{{{_MIN_ENTROPY_LENGTH},}}={{0,2}}")


def looks_like_credential(token: str) -> bool:
    """Whether a token is long and random enough to be worth redacting."""
    return _score(token)
