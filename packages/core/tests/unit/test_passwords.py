"""Argon2id password hashing."""

from __future__ import annotations

import pytest

from factory_core.security import PasswordHasher

pytestmark = pytest.mark.unit

PASSWORD = "correct-horse-battery-staple"


class TestHashing:
    def test_verifies_correct_password(self, password_hasher: PasswordHasher) -> None:
        digest = password_hasher.hash(PASSWORD)

        assert password_hasher.verify(digest, PASSWORD)

    def test_rejects_wrong_password(self, password_hasher: PasswordHasher) -> None:
        digest = password_hasher.hash(PASSWORD)

        assert not password_hasher.verify(digest, PASSWORD + "!")

    def test_hash_is_salted(self, password_hasher: PasswordHasher) -> None:
        """Identical passwords must not produce identical hashes.

        Without a per-hash salt, a leaked table reveals which accounts share a password.
        """
        first = password_hasher.hash(PASSWORD)
        second = password_hasher.hash(PASSWORD)

        assert first != second
        assert password_hasher.verify(first, PASSWORD)
        assert password_hasher.verify(second, PASSWORD)

    def test_hash_uses_argon2id(self, password_hasher: PasswordHasher) -> None:
        assert password_hasher.hash(PASSWORD).startswith("$argon2id$")

    def test_plaintext_absent_from_hash(self, password_hasher: PasswordHasher) -> None:
        assert PASSWORD not in password_hasher.hash(PASSWORD)

    @pytest.mark.parametrize(
        "password",
        ["ünïcödé-pässwörd-123", "  leading and trailing  ", "a" * 128, "🔐🔑 emoji pass"],
    )
    def test_handles_unusual_passwords(
        self, password_hasher: PasswordHasher, password: str
    ) -> None:
        digest = password_hasher.hash(password)

        assert password_hasher.verify(digest, password)


@pytest.mark.failure
class TestMalformedInput:
    @pytest.mark.parametrize(
        "bad_hash",
        ["", "not-a-hash", "$argon2id$garbage", "$2b$12$abcdefghijklmnopqrstuv"],
    )
    def test_corrupt_hash_returns_false(
        self, password_hasher: PasswordHasher, bad_hash: str
    ) -> None:
        """A corrupt stored hash must fail closed, not raise.

        A raised exception would produce a 500 and distinguish corrupt rows from wrong
        passwords, which is information an attacker should not get.
        """
        assert not password_hasher.verify(bad_hash, PASSWORD)

    def test_corrupt_hash_needs_rehash(self, password_hasher: PasswordHasher) -> None:
        assert password_hasher.needs_rehash("not-a-hash")


class TestTimingEqualisation:
    def test_dummy_verify_is_silent(self, password_hasher: PasswordHasher) -> None:
        """Used on the unknown-email path, so it must never raise."""
        password_hasher.verify_dummy()

    def test_dummy_verify_costs_real_work(self, password_hasher: PasswordHasher) -> None:
        """It must actually hash, otherwise it equalises nothing.

        Compared against a real verification rather than an absolute threshold, since
        wall-clock timings vary far too much across machines to assert on directly.
        """
        import time

        digest = password_hasher.hash(PASSWORD)

        start = time.perf_counter()
        password_hasher.verify(digest, PASSWORD)
        real_duration = time.perf_counter() - start

        start = time.perf_counter()
        password_hasher.verify_dummy()
        dummy_duration = time.perf_counter() - start

        assert dummy_duration > real_duration / 10


class TestRehashing:
    def test_stronger_parameters_trigger_rehash(self) -> None:
        """Raising cost must upgrade existing hashes on next sign-in."""
        weak = PasswordHasher(time_cost=1, memory_cost_kib=8192, parallelism=1)
        strong = PasswordHasher(time_cost=3, memory_cost_kib=16384, parallelism=1)

        digest = weak.hash(PASSWORD)

        assert strong.needs_rehash(digest)
        assert not weak.needs_rehash(digest)

    def test_rehashed_password_still_verifies(self) -> None:
        weak = PasswordHasher(time_cost=1, memory_cost_kib=8192, parallelism=1)
        strong = PasswordHasher(time_cost=2, memory_cost_kib=8192, parallelism=1)

        old_digest = weak.hash(PASSWORD)
        assert strong.verify(old_digest, PASSWORD)

        new_digest = strong.hash(PASSWORD)
        assert strong.verify(new_digest, PASSWORD)
        assert not strong.needs_rehash(new_digest)
