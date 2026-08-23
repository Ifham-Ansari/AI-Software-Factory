"""Email verification.

A six-digit code is only ~20 bits, so the code itself is not what makes this safe. Four
rules are:

1. **One live code per account.** Issuing a new one retires the old, so an attacker never
   has two valid targets at once.
2. **Bounded guesses.** Six wrong attempts destroys the code; the user must request
   another. This is what makes online brute force futile.
3. **Short expiry.** Ten minutes bounds the value of a code intercepted in transit.
4. **Bounded issuance.** A cooldown between sends and a daily cap, so the endpoint cannot
   be used to flood someone's inbox or to grind through codes by requesting new ones.

Both limits are enforced in the database rather than a cache. They are abuse controls: a
cache eviction or a restart must not hand an attacker a fresh budget.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from factory_core.application.ports import Clock, SystemClock
from factory_core.config.email import VerificationSettings
from factory_core.domain.audit import AuditAction, AuditRequest
from factory_core.domain.entities import User
from factory_core.domain.ids import new_verification_id
from factory_core.errors import AppError, ErrorCode
from factory_core.infrastructure.email import EmailSender, verification_email
from factory_core.observability import get_logger
from factory_core.persistence.repositories import (
    AuditRepository,
    UserRepository,
    VerificationRepository,
)
from factory_core.security.verification import (
    VerificationStatus,
    codes_match,
    issue_verification_code,
)

logger = get_logger(__name__)


class VerificationError(AppError):
    """The submitted code could not be accepted."""

    code = ErrorCode.VALIDATION_FAILED
    status_code = 400
    message = "That code is not valid."


class CodeExpiredError(VerificationError):
    """The code is past its expiry, or was superseded by a newer one."""

    message = "That code has expired. Request a new one."


class CodeExhaustedError(VerificationError):
    """Too many wrong guesses; the code has been destroyed."""

    message = "Too many incorrect attempts. Request a new code."


class ResendTooSoonError(AppError):
    """A code was requested again before the cooldown elapsed."""

    code = ErrorCode.RATE_LIMITED
    status_code = 429
    message = "A code was just sent. Please wait before requesting another."


class ResendLimitError(AppError):
    """The daily issuance cap has been reached."""

    code = ErrorCode.RATE_LIMITED
    status_code = 429
    message = "Too many codes requested today. Try again tomorrow."


@dataclass(frozen=True, slots=True)
class VerificationChallenge:
    """What the caller needs to know after a code is issued.

    Carries no code and no identifier for it — only how long the user has and when they
    may ask for another.
    """

    email: str
    expires_in_seconds: int
    resend_available_in_seconds: int


class EmailVerificationService:
    """Issues and redeems one-time email verification codes."""

    def __init__(
        self,
        *,
        users: UserRepository,
        verifications: VerificationRepository,
        audit: AuditRepository,
        sender: EmailSender,
        settings: VerificationSettings,
        clock: Clock | None = None,
        request_id: str | None = None,
    ) -> None:
        self._users = users
        self._verifications = verifications
        self._audit = audit
        self._sender = sender
        self._settings = settings
        self._clock = clock or SystemClock()
        self._request_id = request_id

    async def issue(self, user: User, *, enforce_limits: bool = True) -> VerificationChallenge:
        """Mint a code, store it, and email it.

        Args:
            user: The account to verify.
            enforce_limits: Whether the cooldown and daily cap apply. Registration passes
                ``False`` — the user has not asked for anything yet, and refusing the very
                first code because of a cap would be nonsensical.

        Raises:
            ResendTooSoonError: The cooldown has not elapsed.
            ResendLimitError: The daily cap has been reached.
            ServiceUnavailableError: The email could not be sent.
        """
        now = self._clock.now()

        if enforce_limits:
            await self._check_limits(user, now)

        # Retire any live code first: two valid codes would double the guessing surface.
        await self._verifications.invalidate_pending(user.id)

        issued = issue_verification_code(
            verification_id=new_verification_id(),
            user_id=user.id,
            code_length=self._settings.code_length,
            ttl_seconds=self._settings.ttl_seconds,
            max_attempts=self._settings.max_attempts,
            now=now,
        )
        await self._verifications.add(issued.record)

        await self._sender.send(
            verification_email(
                to=user.email,
                display_name=user.display_name,
                code=issued.code,
                expires_in_minutes=self._settings.ttl_minutes,
            )
        )

        # The code is never logged. Only the fact that one was issued.
        logger.info("verification.issued", user_id=str(user.id))
        await self._record(AuditAction.VERIFICATION_SENT, user)

        return VerificationChallenge(
            email=user.email,
            expires_in_seconds=self._settings.ttl_seconds,
            resend_available_in_seconds=self._settings.resend_cooldown_seconds,
        )

    async def verify(self, user: User, code: str) -> User:
        """Redeem a code and mark the address verified.

        Raises:
            CodeExpiredError: No live code, or it has expired.
            CodeExhaustedError: The attempt budget is spent.
            VerificationError: The code is wrong.
        """
        now = self._clock.now()
        record = await self._verifications.latest_for_user(user.id)

        if record is None or not record.is_usable(now=now):
            # Expired, consumed, superseded and exhausted all collapse to one message.
            # Distinguishing them would tell an attacker which codes are worth grinding.
            if record is not None and record.attempts_remaining() == 0:
                raise CodeExhaustedError
            raise CodeExpiredError

        if not codes_match(record.code_hash, code):
            attempts = await self._verifications.record_attempt(record.id)
            remaining = record.max_attempts - attempts
            if remaining <= 0:
                await self._verifications.mark(
                    record.id, VerificationStatus.EXHAUSTED, now=now
                )
                await self._record(AuditAction.VERIFICATION_EXHAUSTED, user)
                logger.warning("verification.exhausted", user_id=str(user.id))
                raise CodeExhaustedError
            await self._record(AuditAction.VERIFICATION_FAILED, user, remaining=remaining)
            raise VerificationError(
                f"That code is not correct. {remaining} attempt"
                f"{'s' if remaining != 1 else ''} remaining."
            )

        await self._verifications.mark(record.id, VerificationStatus.CONSUMED, now=now)
        verified = await self._users.mark_email_verified(user.id, now=now)
        if verified is None:
            raise VerificationError("The account could not be verified.")

        await self._record(AuditAction.VERIFICATION_SUCCEEDED, verified)
        logger.info("verification.succeeded", user_id=str(verified.id))
        return verified

    async def _check_limits(self, user: User, now: datetime) -> None:
        """Apply the resend cooldown and the daily cap."""
        latest = await self._verifications.latest_for_user(user.id)
        if latest is not None:
            elapsed = (now - latest.issued_at).total_seconds()
            if elapsed < self._settings.resend_cooldown_seconds:
                raise ResendTooSoonError

        issued_today = await self._verifications.count_issued_since(
            user.id, since=now - timedelta(days=1)
        )
        if issued_today >= self._settings.max_per_day:
            logger.warning("verification.daily_limit", user_id=str(user.id))
            raise ResendLimitError

    async def _record(self, action: AuditAction, user: User, **metadata: object) -> None:
        await self._audit.record(
            AuditRequest.for_user(action, user.id, **metadata),
            request_id=self._request_id,
            now=self._clock.now(),
        )
