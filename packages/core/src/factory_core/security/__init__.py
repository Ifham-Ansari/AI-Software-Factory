"""Password hashing, tokens, and envelope encryption for the secret vault."""

from factory_core.security.envelope import (
    DecryptionError,
    SealedBytes,
    generate_key,
    seal,
    seal_text,
    unseal,
    unseal_text,
    value_context,
)
from factory_core.security.keyring import KeyRing, MasterKey, build_keyring
from factory_core.security.passwords import PasswordHasher
from factory_core.security.references import (
    InvalidSecretReferenceError,
    SecretReference,
    SecretSink,
    SinkNotAllowedError,
    TracedContextError,
    ensure_resolvable,
    in_traced_context,
    is_secret_reference,
    is_valid_secret_name,
    traced_context,
)
from factory_core.security.refresh import (
    IssuedRefreshToken,
    RefreshTokenRecord,
    RefreshTokenStatus,
    generate_refresh_token,
    hash_refresh_token,
    tokens_match,
)
from factory_core.security.tokens import AccessTokenClaims, AccessTokenIssuer
from factory_core.security.verification import (
    IssuedVerificationCode,
    VerificationCode,
    VerificationStatus,
    codes_match,
    generate_code,
    hash_code,
    issue_verification_code,
)

__all__ = [
    "AccessTokenClaims",
    "AccessTokenIssuer",
    "DecryptionError",
    "InvalidSecretReferenceError",
    "IssuedRefreshToken",
    "IssuedVerificationCode",
    "KeyRing",
    "MasterKey",
    "PasswordHasher",
    "RefreshTokenRecord",
    "RefreshTokenStatus",
    "SealedBytes",
    "SecretReference",
    "SecretSink",
    "SinkNotAllowedError",
    "TracedContextError",
    "VerificationCode",
    "VerificationStatus",
    "build_keyring",
    "codes_match",
    "ensure_resolvable",
    "generate_code",
    "generate_key",
    "generate_refresh_token",
    "hash_code",
    "hash_refresh_token",
    "in_traced_context",
    "is_secret_reference",
    "is_valid_secret_name",
    "issue_verification_code",
    "seal",
    "seal_text",
    "tokens_match",
    "traced_context",
    "unseal",
    "unseal_text",
    "value_context",
]
