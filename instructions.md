# Development Instructions — AI Software Factory

> The operational manual for anyone (human or Claude Code) working on this repository.
> [CLAUDE.md](CLAUDE.md) is the orientation document; **this** is the procedure.
> When the two disagree, fix both — do not pick one.

> **Two rules that override everything else in this file.**
> **1. Claude Code never runs `git commit`, `git push`, `git pull`, or anything that changes
> remote state.** The repository owner does that, by hand, after reading the diff. See §9.
> **2. No work is complete until the pre-push verification in §14 has been run and reported.**
> GitHub is where locally verified code is *confirmed*, not where its errors are *discovered*.

---

## 1. Before you touch anything

Read, in this order:

1. [CLAUDE.md](CLAUDE.md) — what this project is and the rules that never bend.
2. [plan.md](plan.md) — which phase is current and what it covers.
3. [architecture.md](architecture.md) — the design of record.
4. [features.md](features.md) — what is actually built vs. planned.
5. This file — how to do the work.

Then **inspect the real code** before writing any. The documents describe intent; the repository is
the truth. Where they disagree, the repository wins and the documents get corrected.

---

## 2. The development cycle

Every unit of work follows this loop. No step is optional and no step is reordered.

```
READ    → understand the phase scope and what already exists
DESIGN  → decide the module boundaries before writing code
BUILD   → implement the smallest coherent slice
TEST    → unit → integration → failure → e2e
FIX     → until green; no "known failing" left behind
VERIFY  → check acceptance criteria explicitly, one by one
DOC     → update the documents the change invalidated
PROVE   → run the full pre-push verification (§14); fix and re-run until it is green
HAND OFF→ report, and leave the changes in the working tree for the owner to commit (§9)
```

**The rule that catches the most bugs:** run the tests after implementing, before moving on. Not at
the end of the phase. Not "it should work." Run them.

**The rule that catches the rest:** the cycle ends at `HAND OFF`, not at `DOC`. A change that has
not been through §14 is unfinished work, however finished the code looks.

---

## 3. Working on a phase

When asked to "build Phase N":

1. **Scope it.** Open [plan.md](plan.md) §Phase N. List its sub-phases and acceptance criteria
   explicitly before starting. If the scope is ambiguous, resolve it in writing first.
2. **Verify prerequisites.** Confirm Phase N−1 features are `VERIFIED` in
   [features.md](features.md). If they are not, say so and stop. Do not build on unverified ground.
3. **Survey the code.** Read what exists. Do not assume the documents are current.
4. **Mark features `IN_PROGRESS`** in the registry as you pick them up.
5. **Implement sub-phase by sub-phase**, testing each before starting the next.
6. **Verify each acceptance criterion individually**, naming the test that proves it.
7. **Update documentation** (§4).
8. **Report** what was built, what was tested, what passed, what did not, and what you deliberately
   deferred.

### 3.1 Phase boundaries are hard

Do not implement Phase N+1 features while in Phase N — not "while I'm in here", not "it's only a
small addition". Later-phase work built on an unverified foundation is the most expensive kind of
rework in this project.

If Phase N genuinely cannot complete without something scoped to a later phase, that is a **planning
error**. Stop, report it, and get the plan amended. Do not silently pull scope forward.

### 3.2 A phase is complete when

- Every acceptance criterion has a passing test you can name.
- Unit, integration, failure, and (where applicable) e2e suites pass.
- Coverage gates are met.
- No source file exceeds 250 lines.
- All quality gates pass (§6).
- Documentation is updated (§4).
- Every phase feature is `VERIFIED` in the registry.
- The full pre-push verification (§14) has been run and reported green, including the e2e suite.

Compiling is not completing. Demoing once is not completing. Passing the tests you wrote, while the
suite you did not run is red, is not completing.

---

## 4. Documentation protocol

Documentation drift makes every future session slower, because the next reader trusts a document
that has quietly become fiction.

| When you… | Update |
|---|---|
| Complete a feature | `features.md` status + `plan.md` tracker |
| Change architecture | `architecture.md` **and** the ADR in `docs/adr/` |
| Complete a phase | `plan.md`, `features.md`, `CLAUDE.md` status, `architecture.md`, `README.md` |
| Add a dependency | `README.md` + rationale in the PR description |
| Add an environment variable | `.env.example` + `README.md` |
| Make a non-obvious decision | New ADR in `docs/adr/` |
| Discover a doc is wrong | Fix it immediately, in that commit |

**Status honesty.** Never mark a feature `VERIFIED` without a passing test. Never mark a phase
complete with known failures. If something is half-built, the registry says so. An accurate
"blocked" is more useful than an optimistic "done".

---

## 5. Coding standards

### 5.1 File size — 200–250 lines, hard limit

Enforced in CI. When a file approaches 200 lines, split it along responsibility, not arbitrarily:

```
❌ project_service.py (600 lines)
✅ projects/
   ├── service.py       orchestration
   ├── repository.py    persistence
   ├── schemas.py       DTOs
   ├── policies.py      domain rules
   └── errors.py        typed errors
```

Splitting a 600-line file into `service_part1.py` and `service_part2.py` satisfies the linter and
defeats the purpose. If a split does not produce independently nameable, independently testable
units, the design is wrong — fix the design.

**Documented exceptions:** generated files (migrations, `packages/contracts`), lockfiles, and
`packages/core/config/settings.py` if the settings surface genuinely warrants it. Any exception
carries a comment at the top explaining why, and gets a CI allowlist entry.

### 5.2 Python

- Type hints on every function signature. `mypy --strict` passes. No bare `Any` without a comment
  justifying it.
- Pydantic v2 for every boundary: API, LLM output, events, tool I/O, configuration.
- **Never pass unvalidated `dict` between components.** If it crosses a module boundary, it is a
  model.
- Async by default for I/O. Never block the event loop — CPU-bound work goes to a thread or process.
- Functions under ~40 lines. One responsibility each.
- Explicit, typed errors from `packages/core/errors`. Never `except Exception: pass`. Never swallow
  a failure to keep a flow alive.
- Log with `structlog`, always structured, never f-string interpolation of user or secret data.
- Dependencies injected through FastAPI `Depends` or constructor arguments — never module-level
  singletons for anything stateful or I/O-bound.

### 5.3 TypeScript / React

- `strict: true`. `any` requires a comment justifying it.
- Server Components by default; `"use client"` only where interactivity genuinely requires it.
- Types for API and events come from `@factory/contracts` — **never hand-write a backend type**.
- Every data-displaying component handles loading, error, empty, and populated states. All four.
- Components under 200 lines; extract hooks and subcomponents past that.
- Validate at the boundary with Zod, even though the backend also validates.

### 5.4 Layering — enforced, not suggested

`import-linter` runs in CI:

- `packages/core` must not import `langgraph`, `langchain`, or `fastapi`.
- `packages/agents` must not import `fastapi` or `apps.*`.
- `apps/api` and `apps/worker` must not import each other.
- `packages/core/domain` must not import from `application`, `persistence`, or `infrastructure`.

A contract violation is a build failure, not a review comment.

### 5.5 Naming

Say what a thing is. `ProjectSpecification`, not `ProjSpec`. `resolve_secret_for_deployment`, not
`get_secret`. Ambiguous names cost more than long ones — especially in a system where an agent may
read the code later.

---

## 6. Testing rules

### 6.1 Non-negotiable

- **After implementing anything, test it.** Before moving on.
- Every phase ships failure tests. A phase with only happy-path tests is not done.
- Bug fixes start with a failing regression test that reproduces the bug.
- Never assert deterministically against a real LLM. Use fake models with scripted responses.
- Never weaken an assertion to make a test pass. Fix the code or fix the test's premise, and say
  which you did.
- Never mark a test skipped to get green. Quarantine explicitly, with a tracking note.

### 6.2 Test layout

```
packages/core/tests/{unit,integration,security}/
packages/agents/tests/{unit,integration,fakes}/
apps/api/tests/{unit,integration}/
apps/web/{tests,e2e}/
tests/e2e/                      cross-cutting journeys
```

### 6.3 What to test where

| Kind | Rules |
|---|---|
| Unit | No I/O, no network, no LLM. Milliseconds. Test behavior, not implementation |
| Integration | Real Postgres, real Redis, recorded provider fixtures. Test the seam |
| Failure | Dependency down, timeout, malformed input, exhausted retries, permission denied, budget exceeded |
| Security | Traversal, injection, SSRF, sandbox escape, cross-project access. **These must fail to escape** |
| E2E | Real user journeys, fake models for determinism |

### 6.4 Agent testing

Agents are tested with a `FakeModelProvider` returning scripted responses — including malformed ones.
Assert on **structure and control flow**, never on prose:

✅ "The gap analysis identified the database as missing."
❌ "The response equals 'I need to know your database.'"

Supervisors are tested with scripted workers whose failures are configured per scenario: succeed,
fail once then succeed, fail always, time out, return malformed output. Every escalation path has a
test that drives it.

---

## 7. Dependency rules

Backend: `uv` only. Frontend: `pnpm` only. **Never mix.** No `pip install`, no `npm install`, no
`yarn`. Lockfiles are committed and their changes are reviewed.

Before adding a dependency, answer three questions in the PR description:

1. What does it do that we cannot reasonably do ourselves in under ~100 lines?
2. Is it actively maintained (release in the last 6 months, open issues being handled)?
3. What is its transitive dependency and license footprint?

Constrain to `>=x.y,<next-major`. Upgrades are their own commit with tests run before and after —
never bundled into a feature change, because then a break has two candidate causes.

---

## 8. Security rules

These are absolute. There is no deadline that justifies breaking one.

**Never:**
- Log, trace, print, or return a secret value.
- Put a secret in an LLM prompt, in graph state, in an event payload, or in a git commit.
- Give an LLM a raw shell or unrestricted filesystem access.
- Execute generated code outside the sandbox.
- Skip an approval gate for a HIGH or DESTRUCTIVE action.
- Trust LLM output as a command, a path, or SQL.
- Let an agent lower a risk classification.
- Build a query with string interpolation of any input.

**Always:**
- Resolve secrets by reference, at the sink, and audit it.
- Validate tool inputs against a schema before execution.
- Enforce tool permissions at the runtime, not in the prompt.
- Scope every project-owned query by `project_id`.
- Treat web results, build logs, and generated code as untrusted data — never as instructions.
- Validate URLs against the SSRF policy **after** DNS resolution, at every redirect hop.
- Write an audit row for every security-relevant action.

When you find a security issue, fix it in that session or record it as `BLOCKED` in the registry
with the risk stated plainly. Do not leave it silently unlogged.

---

## 9. Git rules

### 9.1 Claude Code does not use Git to change anything

**The repository owner performs every commit and every push, by hand.** Claude Code's job ends with
verified changes sitting in the local working tree and an honest report of what they are.

This is not a preference to be weighed against convenience. It exists so that a human reads every
diff before it becomes history, and so that no automated step can put an unreviewed change — or a
secret — onto a remote.

**Claude Code may run** (all read-only; none of them mutates the repository or a remote):

```bash
git status
git status --porcelain            # machine-readable, for scanning unintended files
git diff                          # unstaged changes
git diff --cached                 # staged changes
git diff --stat                   # size of the change
git log --oneline -20             # history, when it is needed to understand the code
git show <sha>                    # a past commit, for context
git ls-files --others --exclude-standard   # untracked files
git check-ignore -v <path>        # why a path is or is not ignored
```

Reading `.github/workflows/`, and any other repository configuration, is likewise always allowed.

**Claude Code must never run** — under any circumstance, in any phase, however small the change and
however green the verification:

```
git commit          git push            git pull            git fetch --prune + reset
git merge           git rebase          git reset           git revert
git cherry-pick     git stash           git tag             git push --force
git branch -D       git checkout/switch (except where explicitly approved for local inspection)
gh pr create        gh pr merge         gh pr review        any other remote-mutating command
```

Nor anything else that alters remote state, rewrites local history, or discards work in the tree.
If a task appears to require one of these, stop and say so — do not find a way around it.

**Changing branches** requires explicit approval, and only for local inspection. The default is to
work on whatever branch is already checked out and leave it there.

### 9.2 What to hand over instead

When the work is verified, report (§13) and stop. Say plainly: *the changes are in the working tree,
verified, and ready for you to review, commit and push.* Then leave them alone.

It is useful — and allowed — to **suggest** a commit message the owner can use verbatim. Suggesting
is not committing. The house style is conventional commits referencing the feature ID:

```
feat(core): add envelope encryption for project secrets [F-201]
fix(agents): prevent duplicate deploy on interrupt resume [F-311]
test(api): add cross-project access failure cases [F-108]
docs: update architecture for realtime fan-out [F-211]
```

### 9.3 Standards the owner's commits follow

These describe the history this repository keeps. Claude Code's part in them is to leave a working
tree that makes them easy to honour — coherent, scoped, and free of anything that should not be
committed.

- Work lands on a branch named `phase-N/<feature-id>-<slug>`, never directly on `main`.
- Commits are coherent units. Not "wip", not "fixes", not 40 files of unrelated change.
- No secrets, `.env`, credentials, or generated project output — ever, in any commit.
- No `--no-verify`. If a hook fails, the hook found something.
- No force-push of a shared branch.

So: before handing over, make sure the tree contains only the change you intended (§14.12). An
unintended file left in the tree becomes an unintended file in someone's commit.

---

## 10. Handling failures

### 10.1 When your implementation fails

1. Read the actual error. Not the summary — the trace.
2. Reproduce it in a test.
3. Find the root cause. A fix that makes a symptom disappear without an explanation is not a fix.
4. Fix the cause.
5. Confirm the regression test passes and the rest of the suite still does.

**Do not**: retry the same thing hoping for a different result; comment out the failing test;
loosen the assertion; add a `sleep` to hide a race; catch and ignore.

### 10.2 When you are blocked

Say so. State what you tried, what you observed, what you concluded, and what you need. A clear
blocker report is worth more than an hour of guessing. Mark the feature `BLOCKED` with the reason.

### 10.3 When the plan is wrong

Plans are decisions made with less information than you now have. If the plan is wrong, say so
explicitly, propose the amendment, and update [plan.md](plan.md) with the reasoning. Do not silently
deviate — the next session will trust the document.

---

## 11. Common commands

> These are the commands that exist today. Where a command is aspirational it says so — do not put
> an invented script into a document, because the next session will run it and lose an hour.

```bash
# Setup
uv sync --frozen                 # backend dependencies, lockfile respected (as CI installs)
pnpm install --frozen-lockfile   # frontend dependencies (as CI installs)

# Run
uv run dev                       # API + worker + web together
uv run dev-api                   # FastAPI only  (do not invoke uvicorn directly on Windows)
uv run dev-worker                # workflow worker only
pnpm --filter web dev            # Next.js only

# Database
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "description"
uv run alembic downgrade -1

# Test
uv run pytest                                    # everything
uv run pytest packages/core/tests/unit -x        # fast loop
uv run pytest -m integration                     # needs TEST_DATABASE_URL
uv run pytest -m failure
uv run pytest -m security
pnpm --filter web test                           # Vitest component tests
pnpm --filter web test:e2e                       # Playwright, against a running stack

# Quality
uv run ruff check .
uv run ruff format --check .     # `uv run ruff format .` to actually reformat
uv run mypy packages/core/src apps/api/src apps/worker/src scripts
uv run lint-imports              # layering contracts
uv run python scripts/check_file_size.py         # the 250-line rule
pnpm --filter web lint
pnpm -r typecheck                # contracts + web

# Contracts  (OpenAPI → @factory/contracts)
uv run python scripts/export_openapi.py          # regenerate openapi.json
uv run python scripts/export_openapi.py --check  # fail if it has drifted
pnpm --filter @factory/contracts generate        # regenerate packages/contracts/src/api.ts

# Secrets
uv run python scripts/generate_master_key.py     # a new SECRETS__MASTER_KEY
uv run python scripts/rotate_master_key.py       # online key rotation
```

**Not yet real.** There is no `uv run verify-phase N`. A phase's acceptance criteria are verified by
running the suites named against each criterion in [plan.md](plan.md), plus §14. If someone builds
the script later, this section gets the line — and not before.

---

## 12. Definition of done

A change is done when **all** of these hold:

- [ ] It works, and you ran it.
- [ ] Unit tests cover the logic.
- [ ] Integration tests cover the seams it crosses.
- [ ] Failure tests cover what happens when it breaks.
- [ ] The full suite passes — not just your new tests.
- [ ] `ruff`, `mypy --strict`, `lint-imports`, `eslint`, `tsc` all pass.
- [ ] No file exceeds 250 lines.
- [ ] No secret is logged, traced, prompted, or committed.
- [ ] Types are complete; no unjustified `Any`.
- [ ] Errors are explicit and typed.
- [ ] The feature registry is updated.
- [ ] Documentation invalidated by the change is fixed.
- [ ] **The pre-push verification (§14) ran, every applicable check passed, and the report was
      given** — with anything unreproducible locally named explicitly.
- [ ] **The working tree contains the intended change and nothing else** — no scratch files, no
      debug output, no unrelated edits, no secrets.
- [ ] **No commit and no push was performed.** The changes are handed over for the owner (§9).

---

## 13. Reporting

At the end of a work session, report:

1. **What was implemented** — features by ID.
2. **What was tested** — which suites ran, what they cover.
3. **Results** — pass/fail counts, and the *actual output* for anything that failed.
4. **Acceptance criteria** — each one, and the test that proves it.
5. **What is not done** — deferred, blocked, or discovered-but-out-of-scope.
6. **Documentation updated** — which files.
7. **The pre-push verification report** — the §14.15 template, filled in honestly.
8. **The hand-off line** — that the changes are in the working tree, unstaged and uncommitted, ready
   for the owner to review, commit and push.

Report failures plainly. A session that reports "3 tests failing, here is the output, here is my
diagnosis" is more useful than one that reports success and is wrong.

Never write "ready to push" while a single applicable check is failing, unrun, or unknown. "Ready"
is a claim about evidence, and the evidence is the §14 report.

---

## 14. Pre-push verification protocol — mandatory

> **GitHub is where locally verified code is confirmed, not where its errors are discovered.**

This runs after **every** implementation, feature, bug fix, refactor, dependency change,
configuration change and phase completion — before the work is described as complete, and long
before anyone considers pushing it. It is not reserved for large changes. A one-line change to a
Pydantic model can break the generated TypeScript, the frontend build, and four e2e specs.

Scale the protocol to the blast radius of the change, not to its diff size: run every check that
could plausibly be affected, and say which ones you judged inapplicable and why.

### 14.1 Inspect the configuration before running anything

Do not run remembered commands. Read the configuration and derive them, every session — scripts get
renamed, jobs get added, and a protocol that runs yesterday's commands verifies yesterday's project.

Read, at minimum:

- [.github/workflows/](.github/workflows/) — the definition of what "green on GitHub" means
- `package.json` (root, `apps/web`, `packages/contracts`) and `pnpm-workspace.yaml`
- `pyproject.toml` — ruff, mypy, pytest, coverage and import-linter configuration all live here
- `pnpm-lock.yaml`, `uv.lock` — whether the lockfiles changed
- `apps/web/eslint.config.mjs`, `apps/web/tsconfig.json`, `apps/web/vitest.config.ts`,
  `apps/web/playwright.config.ts`
- `alembic.ini` and `packages/core/src/factory_core/migrations/`
- `.env.example` — the environment surface
- `.gitignore` — what must never reach a commit

Then state, in your own words, exactly which CI jobs your change can affect. That list is the
verification you owe.

### 14.2 The check matrix — every CI job, and its local equivalent

Derived from [.github/workflows/ci.yml](.github/workflows/ci.yml). Re-derive it if that file
changes; this table is a convenience, not the authority.

| CI job | CI step | Run locally |
|---|---|---|
| `quality` | install | `uv sync --frozen` |
| `quality` | Ruff lint | `uv run ruff check .` |
| `quality` | Ruff format | `uv run ruff format --check .` |
| `quality` | Mypy strict | `uv run mypy packages/core/src apps/api/src apps/worker/src scripts` |
| `quality` | Import layering | `uv run lint-imports` |
| `quality` | File size limit | `uv run python scripts/check_file_size.py` |
| `backend` | Migrations round trip | `uv run alembic upgrade head && uv run alembic downgrade base && uv run alembic upgrade head` |
| `backend` | Tests + coverage gate | `uv run pytest --cov --cov-report=term-missing --cov-fail-under=85` |
| `contracts` | OpenAPI current | `uv run python scripts/export_openapi.py --check` |
| `contracts` | Generated types current | `pnpm --filter @factory/contracts generate`, then `git diff --exit-code -- packages/contracts/src/api.ts` |
| `frontend` | install | `pnpm install --frozen-lockfile` |
| `frontend` | ESLint | `pnpm --filter web lint` |
| `frontend` | TypeScript | `pnpm --filter @factory/contracts typecheck && pnpm --filter web typecheck` |
| `frontend` | Component tests | `pnpm --filter web test` |
| `frontend` | Production build | `pnpm --filter web build` |
| `e2e` | Playwright, both fan-out states | start the stack, then `pnpm --filter web test:e2e` — see §14.6 |

**On Windows, mypy must be run twice.** mypy narrows `sys.platform` to the host it checks on, so a
Windows-only branch is live locally and unreachable on Linux — which `warn_unreachable` turns into
an error that passes here and fails in CI:

```bash
uv run mypy --platform linux packages/core/src apps/api/src apps/worker/src scripts
```

`git diff --exit-code` in the contracts row is a **read-only** check: it reports whether
regeneration changed the file. It changes nothing and commits nothing. If it fails, the regenerated
file is now in the working tree and belongs in the hand-off (§9.2) — that is the fix, not a problem.

### 14.3 Frontend verification

For any change under `apps/web/` or `packages/contracts/`, run every applicable check:

```bash
pnpm install --frozen-lockfile          # lockfile honest? a mismatch fails CI outright
pnpm --filter web lint                  # ESLint
pnpm -r typecheck                       # contracts + web, including e2e/tsconfig.json
pnpm --filter web test                  # Vitest component tests
pnpm --filter web build                 # production build — see §14.6
```

There is no Prettier configuration in this repository; ESLint is the formatting authority for
TypeScript. Do not invent a `pnpm format` step — report formatting as N/A rather than as passed.

The frontend uses **pnpm**, only. Never `npm`, never `yarn`.

### 14.4 Backend verification

For any change under `packages/core/`, `apps/api/`, `apps/worker/` or `scripts/`:

```bash
uv sync --frozen                                     # lockfile validation
uv run ruff format --check . && uv run ruff check .  # format + lint
uv run mypy packages/core/src apps/api/src apps/worker/src scripts
uv run mypy --platform linux packages/core/src apps/api/src apps/worker/src scripts   # Windows
uv run lint-imports                                  # layering contracts
uv run python scripts/check_file_size.py             # the 250-line rule
uv run pytest --cov --cov-report=term-missing --cov-fail-under=85
```

**Startup and import validation.** A suite full of passing unit tests does not prove the process
starts. Prove it:

```bash
uv run python scripts/export_openapi.py --check   # imports and builds the whole app
uv run dev-api                                    # then hit /health and /ready, then stop it
uv run dev-worker                                 # then confirm "worker.started", then stop it
```

Use `uv run dev-api` / `uv run dev-worker`, never `uvicorn` directly on Windows: uvicorn selects its
own event loop and psycopg's async mode cannot use the `ProactorEventLoop`. Invoking uvicorn by hand
produces a server that starts and then cannot reach the database.

The backend uses **uv**, only. Never `pip`.

### 14.5 Full regression, not just what you touched

Run the whole applicable suite, not the tests you wrote. The purpose is to find what your change
broke somewhere you were not looking.

```bash
uv run pytest                # backend: unit + integration + failure + security
pnpm --filter web test       # frontend components
pnpm --filter web test:e2e   # the whole stack
```

**Integration tests skip without `TEST_DATABASE_URL`.** They print what they cover, but a skip is
not a pass. If they skipped, the report says `SKIPPED — TEST_DATABASE_URL unset`, never `✓`. The
same applies to `TEST_REDIS_URL` and the two-replica fan-out tests.

⚠️ **`TEST_DATABASE_URL` is wiped on every run.** Point it at a throwaway database, never at the one
in `DATABASE_URL`.

A feature is not complete if existing functionality broke. Coverage gates apply to the whole run:
`--cov-fail-under=85`.

### 14.6 Production build

Passing unit tests is not sufficient evidence that the thing builds.

- **Next.js** — `pnpm --filter web build`. This is where server/client boundary mistakes, missing
  `"use client"`, and type errors that Vitest never sees actually surface.
- **FastAPI** — there is no build artefact; the equivalent is import, startup and OpenAPI export
  (§14.4).
- **Docker** — there is no Dockerfile in this repository yet. When `infra/` gains one, a change that
  touches it requires a local `docker build`. Until then this check is N/A, and says so.
- **E2E** — the CI matrix runs the journey twice, with fan-out enabled and unavailable. Locally:

  ```bash
  uv run dev                                            # API + worker + web
  pnpm --filter web exec playwright install chromium    # once
  pnpm --filter web test:e2e
  ```

  The signup specs need `EMAIL__TRANSPORT=console`; with SMTP configured, the debug endpoint that
  serves the verification code correctly refuses. To cover the second matrix leg, run the suite
  again with `REDIS_URL` unset.

### 14.7 Environment and configuration validation

Check, for every change that touches configuration:

- Every new setting is in `.env.example`, with the **exact** name the code reads — including the
  `__` nesting separator (`SECURITY__ARGON2_TIME_COST`, not `SECURITY_ARGON2_TIME_COST`).
- The setting is documented in `README.md` §Configure.
- CI has whatever the change now requires. A setting the app refuses to start without, absent from
  `ci.yml`, is a green local run and a red CI job.
- Frontend and backend agree on URLs, ports and origins.
- No import path points at a file that does not exist; no config references a missing file.
- Production configuration is not weakened to make a check pass.

**Never print a real secret** while verifying. Assert that a variable is set, never what it is.

### 14.8 Database validation

When models, migrations or queries change:

```bash
uv run alembic upgrade head
uv run alembic downgrade base     # a migration that cannot reverse is not finished
uv run alembic upgrade head
uv run pytest -m integration      # requires TEST_DATABASE_URL
```

Also confirm: revision ordering has a single head (`uv run alembic heads`); the models and the
migration agree (an autogenerate against a migrated database produces an empty revision); every
project-owned query is scoped by `project_id`; and the API starts against the configured database.

**Never run any of this against a production or shared database.** Throwaway targets only.

### 14.9 API validation

When routers, DTOs or schemas change:

- Pydantic schemas validate — request, response, and the error shapes.
- `uv run pytest apps/api/tests` passes, including the authentication and authorization cases.
- Cross-project access is still refused (`uv run pytest -m security`).
- OpenAPI regenerates and matches: `uv run python scripts/export_openapi.py --check`.

### 14.10 Frontend/backend contract validation

Any API change is a frontend change. Verify the whole chain, in this order:

```bash
uv run python scripts/export_openapi.py            # backend schema → openapi.json
pnpm --filter @factory/contracts generate          # → packages/contracts/src/api.ts
git diff -- openapi.json packages/contracts/src/api.ts   # read-only: inspect the drift
pnpm -r typecheck                                  # do the consumers still compile?
pnpm --filter web build                            # does it still build?
pnpm --filter web test:e2e                         # does the real request still work?
```

Types in `packages/contracts` are generated. Never hand-edit them, and never make the frontend
compile by widening a generated type — fix the backend schema and regenerate.

### 14.11 Security verification

Before hand-off, confirm:

- No secret, key, token or credential is in the diff — including in a test fixture or a comment.
- No `.env` file is tracked. `.gitignore` still excludes `.env`, `*.pem`, `*.key`, `*.p12`.
- Nothing logs, traces, prints or returns a secret value. Redaction still covers new settings.
- No dependency was added without the §7 questions answered.
- No debug code, no leftover `print`, no commented-out block, no scratch file.
- No shell command is built from unvalidated input; no SQL from string interpolation.
- Tool permissions are still enforced in the runtime, not in a prompt.

`git check-ignore -v <path>` answers "is this actually ignored?" — and note the lesson already
recorded in `.gitignore`: an over-broad ignore rule once silently excluded the entire vault
implementation from the repository. Verify what is ignored; do not assume it.

### 14.12 Review the local Git changes — read-only

```bash
git status
git status --porcelain
git diff
git diff --cached
git ls-files --others --exclude-standard
```

Read the diff. Look for: unintended files, temporary and scratch files, debug artefacts, generated
junk, large binaries, secrets, unrelated modifications, and missing `.gitignore` rules.

Explain what changed and why, in the report. **Do not commit it and do not push it** (§9).

### 14.13 When a check fails

```
Failure
   ↓  read the actual error, not the summary
Diagnose root cause
   ↓  reproduce it in a test, where a test can hold it
Fix the implementation
   ↓
Re-run the failed check
   ↓
Re-run the broader suite the fix could affect
   ↓
Re-run the full applicable verification
   ↓
Repeat until green
```

**Never:** skip a failing test; mark it `xfail` or `skip` to get green; disable a lint rule to pass;
loosen `mypy` or add an unjustified `type: ignore`; weaken an assertion; change a test to hide an
implementation bug; ignore a build error; suppress a warning without a written reason; or report
work complete with a known failure.

If a fix genuinely requires relaxing a rule, that is a decision with a rationale — an ADR in
`docs/adr/`, stated plainly in the report — not a quiet edit to a config file.

### 14.14 Checks that cannot be reproduced locally

Some checks legitimately cannot run on a given machine — no Docker, no Postgres, no Redis, a
Linux-only step. Say so, precisely, in this form:

```text
CHECK NOT REPRODUCIBLE LOCALLY
Check:  backend / integration tests
Reason: TEST_DATABASE_URL is unset; no local PostgreSQL is available.
Risk:   query scoping, constraints, cascades and migration reversal are unproven by this run.
```

Never describe CI as "fully verified" when part of it was not run. An accurate partial verification
is useful; a confident false one costs the next session a day.

### 14.15 The verification report

End every task with this, trimmed to the checks that actually apply, and filled in honestly. `✓`
means it ran and passed. `✗` means it ran and failed. `SKIPPED` and `N/A` mean what they say —
neither may be written as `✓`.

```text
PRE-PUSH VERIFICATION

Frontend
✓/✗ Dependency check      pnpm install --frozen-lockfile
✓/✗ Lint                  pnpm --filter web lint
✓/✗ Type check            pnpm -r typecheck
✓/✗ Tests                 pnpm --filter web test           (n passed)
✓/✗ Production build      pnpm --filter web build
N/A Format                no Prettier configuration in this repository

Backend
✓/✗ Dependency check      uv sync --frozen
✓/✗ Format                uv run ruff format --check .
✓/✗ Lint                  uv run ruff check .
✓/✗ Type check            uv run mypy ...  (and --platform linux on Windows)
✓/✗ Layering              uv run lint-imports
✓/✗ File size             uv run python scripts/check_file_size.py
✓/✗ Tests                 uv run pytest --cov --cov-fail-under=85   (n passed, x% coverage)
✓/✗ Startup / import      dev-api /health + /ready, dev-worker started

Integration
✓/✗ Integration tests     uv run pytest -m integration
✓/✗ API contract          export_openapi.py --check + contracts generate + diff
✓/✗ E2E                   pnpm --filter web test:e2e       (fan-out enabled / unavailable)

Database
✓/✗ Migration round trip  upgrade head -> downgrade base -> upgrade head
✓/✗ Database tests

Security
✓/✗ No secrets in the diff, no .env tracked, no secret logged
✓/✗ Dependency and configuration review

CI
✓/✗ GitHub workflow checks reproduced locally
    (list anything not reproducible, in the §14.14 form)

Git
✓ Changes reviewed        git status / diff / diff --cached
✓ No secrets
✓ No unintended files
✓ No unrelated changes

Git Operations
✓ No commit performed
✓ No push performed
✓ No remote repository changes performed

RESULT: READY FOR MANUAL COMMIT/PUSH
```

`RESULT: READY FOR MANUAL COMMIT/PUSH` may only be written when every applicable line is `✓`.
Otherwise the result is `NOT READY`, followed by what failed and what you intend to do about it.

---

## 15. Change log

| Date | Change |
|---|---|
| 2026-08-23 | Initial operational manual. |
| 2026-08-26 | Git rules rewritten (§9): Claude Code performs no commit, push, or any other remote- or history-changing operation — the repository owner does that, by hand, after reading the diff. Mandatory pre-push verification protocol added (§14), with the CI-job-to-local-command matrix and the report template. §11 corrected to the commands that actually exist: `verify-phase` and `generate-contracts` never did. |
