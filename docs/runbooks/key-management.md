# Runbook — Master key management

> **Losing the master key makes every stored secret permanently unrecoverable.** There is
> no recovery path, by design: the key is never written to the database, so a database
> backup does not contain it. Back it up before storing anything real.

Applies to `SECRETS__MASTER_KEY` (F-201, F-216).

---

## 1. What the key does

Two layers of encryption, so the outer key can be rotated without re-encrypting every
stored value:

```
SECRETS__MASTER_KEY (KEK)          environment only, never in the database
  └── wraps a per-project DEK      stored wrapped in project_keys.wrapped_dek
        └── encrypts secret values AES-256-GCM, in secrets.ciphertext
```

Rotating the KEK re-wraps each project's DEK. The DEK itself is unchanged, so the values
it encrypts stay readable — that is the entire point of the two layers.

Format: `<version>:<base64-encoded 32 bytes>`, e.g. `v1:3q2+7w...`. The version travels
inside every wrapped DEK (`project_keys.wrapped_dek` starts with it), so unwrapping never
has to guess which key was used.

---

## 2. Generating a key

```bash
uv run python scripts/generate_master_key.py --version v1
```

Prints one line ready to paste into `.env`. It is written nowhere — piping it to a file is
your decision, deliberately not automated.

**Back it up immediately**, to whatever your organisation uses for break-glass material
(a password manager's secure note, a sealed envelope, a KMS). Losing it is unrecoverable.

---

## 3. Verifying the key is live

```bash
uv run python -c "
from factory_core.config import load_settings
from factory_core.security.keyring import build_keyring
ring = build_keyring(load_settings().secrets)
print('active version:', ring.active_version)
print('can unwrap    :', sorted(ring.known_versions))
"
```

The API also reports it at startup, as a boolean and never a value:

```
api.started integrations={'secrets': True, ...}
```

`'secrets': False` means the vault is unconfigured. Storing a secret then returns 503 with
`configuration_invalid` rather than falling back to storing it in the clear.

---

## 4. Rotating the key

Rotation is **online**. Existing secrets stay readable throughout, because the retired key
remains loaded until every DEK has been re-wrapped.

### Step 1 — generate the successor

```bash
uv run python scripts/generate_master_key.py --version v2
```

### Step 2 — deploy both keys

Promote the new key to active and demote the old one, in the same deployment:

```ini
SECRETS__MASTER_KEY=v2:<new material>
SECRETS__PREVIOUS_KEYS=v1:<old material>
```

At this point: new DEKs are wrapped with `v2`; existing DEKs still unwrap with `v1`.
Nothing has broken and nothing is yet re-wrapped.

### Step 3 — re-wrap every project DEK

```bash
uv run python scripts/rotate_master_key.py
```

Idempotent and resumable — it re-wraps only rows whose `key_version` is not the active
one, so interrupting it and re-running is safe.

### Step 4 — confirm nothing references the old version

```sql
SELECT key_version, count(*) FROM project_keys GROUP BY key_version;
```

Proceed only when every row reports the active version.

### Step 5 — drop the retired key

```ini
SECRETS__MASTER_KEY=v2:<new material>
SECRETS__PREVIOUS_KEYS=
```

Keep the retired key in your backup store for as long as you retain database backups
taken before step 3 — restoring one of those would reintroduce `v1`-wrapped rows.

---

## 5. Failure modes

| Symptom | Cause | Action |
|---|---|---|
| Startup fails naming `SECRETS__MASTER_KEY` | Malformed, wrong length, or not base64 | Re-check the pasted value; it must decode to exactly 32 bytes |
| `503 configuration_invalid` on storing a secret | No master key configured | Set `SECRETS__MASTER_KEY` and restart |
| `DecryptionError` reading one project's secrets | That project's DEK was wrapped with a key no longer in configuration | Restore the retired key to `SECRETS__PREVIOUS_KEYS`, then complete step 3 |
| `DecryptionError` reading *every* secret | Wrong master key entirely | Restore the correct key from backup. Do not re-generate — a new key cannot decrypt existing data |
| Startup fails with "duplicate master key versions" | The same version appears in both variables | Remove it from `SECRETS__PREVIOUS_KEYS` |

**If the key is genuinely lost**, the stored secrets are gone. The recovery procedure is
to delete the affected `project_keys` and `secrets` rows and re-collect the credentials
from their owners. There is no cryptographic alternative — that is the property the design
is buying.

---

## 6. Handling rules

- Never commit a key. `.env` is gitignored; `.env.example` carries placeholders only.
- Never log one. Configuration secrets are registered with the redactor at startup, so a
  key that reached a log line would be printed as `[REDACTED]` — but do not rely on that
  as the primary control.
- Never pass one to an agent or put it in graph state. Agents receive `secret://`
  references, and the resolver refuses to run inside a traced context.
- Rotate on a schedule, and immediately on suspected exposure or an operator offboarding.

---

## 7. Verification

The rotation guarantees have tests:

| Property | Test |
|---|---|
| Rotation preserves access to existing values | `test_envelope_crypto.py::TestKeyRing::test_rotation_preserves_access_to_existing_values` |
| A retired version is detected for re-wrapping | `test_envelope_crypto.py::TestKeyRing::test_needs_rewrap_identifies_retired_versions` |
| An unknown version fails closed | `test_envelope_crypto.py::TestKeyRing::test_unknown_version_fails_closed` |
| Duplicate versions are refused at startup | `test_envelope_crypto.py::TestKeyRing::test_duplicate_versions_are_refused` |
| A wrapped DEK cannot be moved between projects | `test_envelope_crypto.py::TestKeyRing::test_wrapped_dek_is_bound_to_its_project` |
