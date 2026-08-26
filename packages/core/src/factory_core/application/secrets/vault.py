"""The secret vault.

This service is the only code in the system that turns ciphertext into a plaintext
credential. Everything it enforces is enforced here rather than at call sites, because a
rule that has to be remembered at every call site is a rule that will eventually be
forgotten at one:

* **Write-only reads.** :meth:`SecretVault.list_secrets` and :meth:`describe` return
  metadata. Only :meth:`resolve` produces a value, and it demands a sink and a purpose.
* **Sink allowlist and traced-context refusal.** Delegated to
  ``security.references.ensure_resolvable`` so the policy has one definition.
* **Every resolution is audited**, including refusals — a denied attempt is the row an
  investigation wants most, so it is written before the exception propagates.
* **Per-project DEKs.** A project's key is created on first write and never shared, so
  compromising one project's DEK reveals nothing about another's.

The plaintext returned by :meth:`resolve` is a ``SecretStr``. That does not make it safe —
it makes it *loud*: printing one shows ``**********``, so extracting the value requires
writing ``.get_secret_value()``, which is greppable and reviewable.
"""

from __future__ import annotations

from pydantic import SecretStr

from factory_core.application.secrets.schemas import (
    ResolutionRequest,
    SecretView,
    StoreSecretCommand,
)
from factory_core.domain.ids import ProjectId
from factory_core.errors import NotFoundError
from factory_core.observability import get_logger
from factory_core.persistence.models_secrets import SecretRow
from factory_core.persistence.repositories.secrets import (
    ProjectKeyRepository,
    SecretAccessLogRepository,
    SecretRepository,
)
from factory_core.security.envelope import seal_text, unseal_text, value_context
from factory_core.security.keyring import KeyRing
from factory_core.security.references import (
    SecretReference,
    SecretSink,
    ensure_resolvable,
)

logger = get_logger(__name__)


class SecretVault:
    """Stores, describes and resolves a single project's secrets."""

    def __init__(
        self,
        *,
        secrets: SecretRepository,
        project_keys: ProjectKeyRepository,
        access_log: SecretAccessLogRepository,
        keyring: KeyRing,
    ) -> None:
        self._secrets = secrets
        self._project_keys = project_keys
        self._access_log = access_log
        self._keyring = keyring

    @property
    def project_id(self) -> ProjectId:
        """The project this vault is bound to."""
        return self._secrets.project_id

    async def store(self, command: StoreSecretCommand) -> SecretView:
        """Encrypt and store a value.

        The value is encrypted under the project's DEK and bound to its own name, so the
        ciphertext is useless in any other row.
        """
        dek = await self._project_dek()
        context = value_context(str(self.project_id), command.name)
        ciphertext = seal_text(dek, command.value.get_secret_value(), context=context)

        row = await self._secrets.upsert(
            command.name,
            ciphertext=ciphertext,
            key_version=self._keyring.active_version,
            description=command.description,
        )
        # Name and version only. The value is never logged, and neither is its length,
        # which would leak something about the credential's shape.
        logger.info(
            "secret.stored",
            project_id=str(self.project_id),
            secret_name=command.name,
            version=row.version,
        )
        return _to_view(row, self.project_id)

    async def list_secrets(self) -> list[SecretView]:
        """Metadata for every secret this project holds."""
        rows = await self._secrets.list_names()
        return [_to_view(row, self.project_id) for row in rows]

    async def describe(self, name: str) -> SecretView:
        """Metadata for one secret.

        Raises:
            NotFoundError: No such secret in this project.
        """
        row = await self._secrets.get(name)
        if row is None:
            raise NotFoundError("The requested secret was not found.")
        return _to_view(row, self.project_id)

    async def delete(self, name: str) -> bool:
        """Remove a secret. Returns whether one existed."""
        deleted = await self._secrets.delete(name)
        if deleted:
            logger.info("secret.deleted", project_id=str(self.project_id), secret_name=name)
        return deleted

    async def resolve(
        self, name: str, *, sink: SecretSink, request: ResolutionRequest
    ) -> SecretStr:
        """Decrypt a secret for use at an allowlisted sink.

        Every outcome is audited before it returns or raises, so the log records refusals
        as well as grants.

        Raises:
            SinkNotAllowedError: ``sink`` is not a recognised sink.
            TracedContextError: Called inside a traced span.
            NotFoundError: No such secret.
            DecryptionError: The stored value could not be decrypted.
        """
        try:
            ensure_resolvable(sink)
        except Exception:
            await self._audit(name, sink=sink, request=request, granted=False)
            raise

        row = await self._secrets.get(name)
        if row is None:
            await self._audit(name, sink=sink, request=request, granted=False)
            raise NotFoundError("The requested secret was not found.")

        dek = await self._project_dek()
        context = value_context(str(self.project_id), name)
        plaintext = unseal_text(dek, bytes(row.ciphertext), context=context)

        await self._secrets.mark_accessed(name)
        await self._audit(name, sink=sink, request=request, granted=True)
        logger.info(
            "secret.resolved",
            project_id=str(self.project_id),
            secret_name=name,
            sink=sink.value,
            purpose=request.purpose,
        )
        return SecretStr(plaintext)

    async def resolve_reference(
        self, reference: SecretReference, *, sink: SecretSink, request: ResolutionRequest
    ) -> SecretStr:
        """Resolve a parsed ``secret://`` reference.

        Raises:
            NotFoundError: The reference points at a different project. Reported as "not
                found" rather than "forbidden" so a caller cannot use this to discover
                which secrets exist elsewhere.
        """
        if reference.project_id != str(self.project_id):
            raise NotFoundError("The requested secret was not found.")
        return await self.resolve(reference.name, sink=sink, request=request)

    async def _project_dek(self) -> bytes:
        """Return this project's data encryption key, creating one on first use.

        Created lazily rather than at project creation so that a deployment which never
        stores a secret never generates key material it does not need.
        """
        row = await self._project_keys.get(self.project_id)
        if row is None:
            dek = self._keyring.generate_dek()
            wrapped = self._keyring.wrap_dek(dek, project_id=str(self.project_id))
            await self._project_keys.create(
                self.project_id,
                wrapped_dek=wrapped,
                key_version=self._keyring.active_version,
            )
            logger.info("project_key.created", project_id=str(self.project_id))
            return dek
        return self._keyring.unwrap_dek(row.wrapped_dek, project_id=str(self.project_id))

    async def _audit(
        self,
        name: str,
        *,
        sink: SecretSink,
        request: ResolutionRequest,
        granted: bool,
    ) -> None:
        """Write one access-log row."""
        await self._access_log.record(
            project_id=self.project_id,
            secret_name=name,
            sink=sink.value if isinstance(sink, SecretSink) else str(sink),
            purpose=request.purpose,
            actor_type=request.actor_type,
            actor_id=request.actor_id,
            run_id=request.run_id,
            request_id=request.request_id,
            granted=granted,
        )


def _to_view(row: SecretRow, project_id: ProjectId) -> SecretView:
    """Project a stored row onto its metadata-only view.

    The ciphertext is present on ``row`` and simply not read. That is the point: the
    conversion to a client-facing shape is where the value is dropped, and there is no
    field on :class:`SecretView` that could carry it.
    """
    return SecretView(
        name=row.name,
        description=row.description,
        is_set=True,
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
        last_accessed_at=row.last_accessed_at,
        reference=str(SecretReference(project_id=str(project_id), name=row.name)),
    )
