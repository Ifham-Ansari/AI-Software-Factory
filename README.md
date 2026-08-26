# AI Software Factory

A hierarchical, supervised autonomous software engineering and deployment system. Describe an
application in natural language; an organization of AI agents plans it, builds it, tests it, deploys
it, and hands you live URLs — escalating every high-risk decision to a human.

> ## Status: Phase 2 complete — secrets and the realtime backbone
>
> **Phase 1** — registration with email verification, sign-in, rotating refresh tokens with
> theft detection, per-owner project CRUD, an audit trail, structured logging with secret
> redaction, generated TypeScript contracts, and a Next.js control centre.
>
> **Phase 2** — an envelope-encrypted secret vault that no endpoint can read back, config
> requirement tracking, Redis rate limiting/idempotency/locks, durable per-run events with
> gapless sequence numbers, a ticket-authenticated WebSocket with lossless reconnect, and a
> Postgres job queue with a worker that drains on SIGTERM.
>
> **No AI agents yet** — those start in Phase 3. Everything above exists so the agent
> runtime has somewhere safe to put credentials and something durable to run on.
>
> 614 backend tests (89% coverage) · 53 frontend tests · 16 end-to-end specs — all green
> against real PostgreSQL and the full stack.
>
> See [plan.md](plan.md) for the roadmap and [features.md](features.md) for exact status.

---

## What it does

```
"Build a restaurant management system with authentication, a dashboard,
 inventory management, PostgreSQL, FastAPI, Next.js, tests, and deployment."
                              ↓
   Requirements analysis → identifies what's missing → asks you
                              ↓
   Architecture + OpenAPI contract → task decomposition
                              ↓
   Backend · Frontend · Database agents build in parallel
                              ↓
   Tests generated and run → failures diagnosed and fixed autonomously
                              ↓
   Security review → quality gate
                              ↓
   Database provisioned → migrations dry-run on a branch → your approval → applied
                              ↓
   Deployed → health verified → 🚀 live URLs
```

At every high-risk step — a production deployment, a destructive migration, a billable resource —
the run **pauses durably** and waits for you.

## What makes it different

Most multi-agent demos are agents calling agents. This one is built around **supervision**:

- **Real hierarchy.** Executive → department supervisors → workers → tools. Four levels, and each
  supervisor genuinely validates its department's output against explicit acceptance criteria.
- **Failure as control flow.** A seven-class error taxonomy routes failures to backoff,
  analyst-driven diagnosis, reassignment, or a human. Four independent guards make infinite loops
  structurally impossible.
- **Human control that actually works.** LangGraph interrupts + Postgres checkpoints mean a paused
  run holds **no process open**. It can wait days across platform restarts and resume exactly.
- **Secrets that never reach a model.** Envelope encryption; agents get `secret://` references;
  values are resolved only at three audited sinks and never enter a prompt, a trace, or graph state.
- **Generated code treated as hostile.** It executes only inside a hardened container with network
  egress denied by default. Agents get typed tools, never a shell.
- **Measured, not asserted.** Phase 8 puts agent and supervisor quality under LangSmith evaluation
  with a CI regression gate.

## Architecture at a glance

```mermaid
flowchart LR
    W["Next.js<br/>Control Center"] <-->|"REST + WS"| A["FastAPI"]
    A -->|"enqueue in txn"| Q[("Postgres<br/>job queue")]
    Q --> K["Workflow<br/>Worker"]
    K --> G["LangGraph<br/>Engine"]
    G --> T["Permissioned<br/>Tools"]
    G <-->|"checkpoints"| P[("Neon<br/>Postgres")]
    K -->|"events"| R[("Upstash<br/>Redis")]
    R -->|"fan-out"| A
    T --> X["Neon · GitHub<br/>Vercel · Render"]
    G --> L["LangSmith"]
```

The API never runs a graph. Runs execute in a separate worker process so an API restart cannot kill
one. Events are persisted before they are published, so a reconnecting browser replays from a
sequence number rather than losing history.

Full detail: [architecture.md](architecture.md).

## Technology

| Layer | Stack |
|---|---|
| **Frontend** | Next.js 16 (App Router, RSC) · TypeScript strict · pnpm · Node 24 LTS |
| **Backend** | Python 3.13 · FastAPI · Pydantic v2 · SQLAlchemy 2.0 · Alembic · uv |
| **AI** | LangGraph 1.2 · LangChain 1.x · LangSmith · OpenAI |
| **Data** | Neon Postgres · pgvector · Upstash Redis |
| **Quality** | pytest · Vitest · Playwright · ruff · mypy --strict · import-linter |
| **Ops** | structlog · OpenTelemetry · Docker |

Every choice, with the alternative it beat, is in [architecture.md](architecture.md) §15.

---

## Getting started

### Requirements

- Python 3.13 and [uv](https://docs.astral.sh/uv/) — uv installs the right Python for you
- Node 22+ and pnpm
- A PostgreSQL database — a [Neon](https://neon.com) project, or Docker locally
- Optionally [Upstash Redis](https://upstash.com), for cross-replica event fan-out. The
  platform works without it: events stay durable and clients replay over REST.

Later phases add more: OpenAI and LangSmith (Phase 3), Docker for the code sandbox
(Phase 5), GitHub/Vercel/Render tokens (Phases 5 and 7). Neither is needed to run what
exists today.

If you already have those credentials, put them in `.env` now — configuration for OpenAI
and LangSmith exists and validates them, and registers them with the log redactor at
startup. Nothing consumes them yet; `/ready` simply reports which are configured.

### Install

```bash
git clone <repo-url> && cd "AI Software Factory"
uv sync          # backend workspace
pnpm install     # frontend workspace
```

### Configure

```bash
cp .env.example .env
```

Fill in the required values. The application **fails fast at startup** if a required variable is
missing, naming the variable.

Two variables are required, and a third is required for the secret vault:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string. A plain `postgresql://` URL is rewritten to the psycopg driver automatically, so a pasted Neon string works unmodified |
| `JWT_SECRET_KEY` | Signs access tokens. At least 32 characters; startup refuses anything shorter |
| `SECRETS__MASTER_KEY` | Encrypts stored project credentials. Without it the platform runs, but storing a secret returns 503 rather than falling back to storing it in the clear |

```bash
# Signing key
python -c "import secrets; print(secrets.token_urlsafe(48))"

# Master key for the secret vault
uv run python scripts/generate_master_key.py
```

> ⚠️ **Losing `SECRETS__MASTER_KEY` makes every stored secret permanently unrecoverable.**
> It is never written to the database, so a database backup does not contain it. Back it up
> before storing anything real, and read
> [docs/runbooks/key-management.md](docs/runbooks/key-management.md) — it covers online
> rotation, which needs no downtime.

`REDIS_URL` is optional. Without it the platform works and every event is still durable in
PostgreSQL; a browser recovers what it missed by replaying over REST. Redis buys latency,
not correctness.

Everything else has a working default — see [.env.example](.env.example), which documents
each one and what it does.

The frontend needs `API_BASE_URL` in `apps/web/.env.local` if the API is not on
`http://127.0.0.1:8000`. It is deliberately **not** a `NEXT_PUBLIC_` variable: the browser
never calls the REST API directly, so nothing about the backend's location reaches the
bundle.

The one exception is the event WebSocket, which cannot be proxied through a Next.js route
handler. Its origin defaults to `API_BASE_URL` with `http` swapped for `ws`; override it
with `WS_BASE_URL` when the API is behind a different public hostname. It is still not
public — the URL is returned by the authenticated ticket route, and the handshake requires
a single-use ticket regardless.

⚠️ **Never put a real secret in `.env.example`.** It is committed. Real values belong in
`.env`, which is gitignored.

### Database

```bash
uv run alembic upgrade head
```

### Run

One command starts everything:

```bash
uv run dev
```

Output is prefixed per process, and Ctrl+C stops all three. Or run them separately, which
gives clearer output when debugging one of them:

```bash
uv run dev-api               # FastAPI      → http://127.0.0.1:8000  (docs at /docs)
uv run dev-worker            # workflow worker (a process shell until Phase 2)
pnpm --filter web dev        # Next.js      → http://127.0.0.1:3000
```

Then open http://127.0.0.1:3000 and register an account.

#### Where the verification code goes

Registration emails a 6-digit code, and the account cannot sign in until it is redeemed.
Out of the box `EMAIL__TRANSPORT=console`, which means **the code is printed in the
`uv run dev-api` terminal rather than emailed** — no mail account needed to develop:

```
[warning] email.console_transport  to=you@example.com
    Your verification code is: 047743
```

To send real mail instead, set the SMTP block in `.env`. With Gmail:

1. Turn on 2-Step Verification — <https://myaccount.google.com/security>
2. Create an **App Password** (16 characters) — <https://myaccount.google.com/apppasswords>
   Your normal Google password will not work; Google disabled it for SMTP in 2022.
3. Fill in and switch the transport:

```ini
EMAIL__TRANSPORT=smtp
EMAIL__FROM_ADDRESS=you@gmail.com     # must match SMTP_USERNAME, or Google rejects it
EMAIL__SMTP_HOST=smtp.gmail.com
EMAIL__SMTP_PORT=587
EMAIL__SMTP_USERNAME=you@gmail.com
EMAIL__SMTP_PASSWORD=abcd efgh ijkl mnop
```

Startup validates this and refuses to run on a configuration that cannot deliver — a
missing host, a sender left as the placeholder, or a username without a password — so a
typo surfaces as a named variable at boot rather than as a failed signup.

Prefer not to use a personal mailbox? Point it at a local catcher and read the mail in a
browser — no credentials, nothing leaves the machine:

```bash
docker run -d -p 1025:1025 -p 8025:8025 axllent/mailpit   # inbox at :8025
```
```ini
EMAIL__TRANSPORT=smtp
EMAIL__FROM_ADDRESS=dev@example.com
EMAIL__SMTP_HOST=127.0.0.1
EMAIL__SMTP_PORT=1025
EMAIL__SMTP_USE_TLS=false
```

`console` is refused in production, because it would write a live credential into a log
aggregator.

> **On Windows, start the backend with `uv run dev-api`, not `uvicorn` directly.**
> psycopg's async mode cannot use Windows' default `ProactorEventLoop`, and uvicorn selects
> its loop through a factory that ignores the asyncio policy. `dev-api` owns the loop and
> picks a compatible one; invoking uvicorn yourself produces an `InterfaceError` on the
> first query that reads like a connectivity problem. Linux is unaffected.

### Realtime and the job queue

Open a project and the page shows a live activity feed with a connection indicator.
"Run a test job" enqueues a `noop` job; the worker claims it, emits progress events, and
they arrive over the WebSocket within a second or two.

That path is the whole Phase 2 backbone end to end — enqueue in a transaction, claim with
`SKIP LOCKED`, execute, persist with a per-run sequence number, publish through Redis, fan
out to the browser. It exists to prove the pipeline before any agent needs it.

**Reconnection is lossless.** Kill your network, run another job, and reconnect: the client
replays from the last sequence number it saw, so the feed fills the gap with no duplicates.
That works even with Redis stopped — the socket goes quiet, the events stay durable, and
the replay delivers them.

```bash
# Watch the worker claim and run jobs
uv run dev-worker
```

### Test

```bash
uv run pytest                              # all backend tests (~20s)
uv run pytest packages/core/tests/unit -x  # fast feedback loop (~3s)
uv run pytest -m security                  # isolation, redaction, enumeration resistance
uv run pytest -m failure                   # adversarial and fault-injection cases
pnpm --filter web test                     # component tests
pnpm --filter web test:e2e                 # end-to-end (needs the full stack running)
```

**Integration tests need a real database.** Without `TEST_DATABASE_URL` they skip — loudly,
with a message saying what they cover. They prove what in-memory fakes structurally cannot:
that the generated SQL really scopes by owner, that constraints and cascades behave as
declared, and that migrations reverse.

⚠️ **The target database is wiped on every run.** Point it at a throwaway, never at the
database in `DATABASE_URL`.

Either use a local container:

```bash
docker run -d --name factory-test-db -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:17-alpine
# then in .env:
TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres
```

…or a separate database on the same Neon project — same connection string with the
database name changed:

```
DATABASE_URL=postgresql://user:pw@ep-xxx.neon.tech/neondb?sslmode=require
TEST_DATABASE_URL=postgresql://user:pw@ep-xxx.neon.tech/factory_test?sslmode=require
```

Create it once with `CREATE DATABASE factory_test;`. `.env` is read by the test suite, so
no export is needed.

CI provisions a `postgres:17` service automatically; see
[.github/workflows/ci.yml](.github/workflows/ci.yml).

### End-to-end

Playwright drives a real browser against the running stack, so start it first:

```bash
uv run dev                            # or the three commands separately
pnpm --filter web exec playwright install chromium   # once
pnpm --filter web test:e2e
```

> **The signup specs need `EMAIL__TRANSPORT=console`.** They read the verification code
> from a debug endpoint that only exists in development/test, and that endpoint serves the
> console transport only — it refuses to hand out a code once real mail is configured,
> which is the point of it. If your `.env` is set to `smtp`, start the API with the
> transport overridden for the run:
>
> ```bash
> EMAIL__TRANSPORT=console uv run dev-api      # PowerShell: $env:EMAIL__TRANSPORT="console"
> ```
>
> CI is unaffected: it has no `.env`, so it already defaults to `console`.

### Quality gates

Everything CI enforces, runnable locally:

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy packages/core/src apps/api/src apps/worker/src scripts
uv run lint-imports                         # layering contracts
uv run python scripts/check_file_size.py    # the 250-line rule
pnpm --filter web lint
pnpm -r typecheck
```

> **On Windows, also run mypy the way CI will.** mypy narrows `sys.platform` to the host
> it is checking on, so a Windows-only branch is live locally and *dead code* on Linux —
> which `warn_unreachable` reports as an error. That passes here and fails in CI:
>
> ```bash
> uv run mypy --platform linux packages/core/src apps/api/src apps/worker/src scripts
> ```
>
> Guard platform-specific code with a positive `if sys.platform == "win32":` block rather
> than an early `if sys.platform != "win32": return`. mypy skips a guarded block silently,
> but treats statements after an always-taken return as unreachable. Both functions in
> `packages/core/src/factory_core/runtime.py` are written that way for this reason.

`lint-imports` enforces layering: `core` may not import a web framework, `domain` may not
import SQLAlchemy, and the API and worker must stay independent processes. A violation
fails the build rather than becoming a review comment.

### LangSmith

Set `LANGSMITH_TRACING=true` plus `LANGSMITH_API_KEY` and `LANGSMITH_PROJECT`. Every graph node,
agent call, and tool invocation is traced with project/run/task IDs and the prompt version.
Redaction hooks strip secrets before anything leaves the process.

---

## Repository structure

```
apps/
  api/          FastAPI — routers, DTOs, middleware, WebSocket
  worker/       workflow executor process
  web/          Next.js control center
packages/
  core/         domain, application, persistence, infrastructure   (no LangGraph, no FastAPI)
  agents/       graphs, supervisors, workers, tools, prompts       (no FastAPI)
  contracts/    generated TypeScript types — never hand-edited
infra/          docker, compose, sandbox image, provider config
docs/           adr/ · runbooks/ · evaluation/
scripts/        dev, codegen, db, verify-phase
tests/          cross-cutting end-to-end suites
```

## Development workflow

```
Read docs → inspect code → design → implement → TEST → fix → verify criteria
          → document → pre-push verification → hand off for commit
```

Phases are built strictly in order, and a phase is complete only when its acceptance criteria have
passing tests — not when the code compiles. Full procedure in [instructions.md](instructions.md).

Three rules that matter more than the rest: **after implementing anything, test it before moving
on**; **no source file exceeds 250 lines** (enforced in CI); and **every change goes through the
pre-push verification** in [instructions.md](instructions.md) §14 — every applicable CI job
reproduced locally — before it is called done.

**Git is done by hand.** Claude Code and any other assistant working in this repository may read the
repository (`git status`, `git diff`, `git log`) but never commit, push, or change remote state.
Verified changes are left in the working tree for a human to review and commit.

## Roadmap

| Phase | Delivers | Status |
|---|---|---|
| 1 | Platform foundation, auth, projects, contracts, CI | **Complete** |
| 2 | Secret vault, event bus, WebSocket, job queue, project UI | **Complete** |
| 3 | Agent runtime, tool framework, budgets, HITL, intake | Not started |
| 4 | Hierarchical supervision, parallelism, recovery, arbitration | Not started |
| 5 | Sandboxed workspace, code generation, git | Not started |
| 6 | Test generation, security review, autonomous fix loop | Not started |
| 7 | Neon provisioning, migration pipeline, deployment, health | Not started |
| 8 | LangSmith evaluation, RAG, quotas, monitoring, hardening | Not started |

Details, acceptance criteria, and risks per phase: [plan.md](plan.md).

## Documentation

| File | What it is |
|---|---|
| [CLAUDE.md](CLAUDE.md) | Orientation and non-negotiable rules — **read first** |
| [plan.md](plan.md) | Phase roadmap, acceptance criteria, decisions, risks |
| [architecture.md](architecture.md) | Design of record with diagrams |
| [features.md](features.md) | Feature registry — 127 features and their real status |
| [instructions.md](instructions.md) | Development procedure and standards |
| `docs/adr/` | Architecture decision records |
| `docs/runbooks/` | Operational procedures |

## Security

Secrets are never logged, traced, prompted, or returned. Generated code executes only in an isolated
container with egress denied by default. Agents receive typed, permissioned tools — never a shell.
Tool permissions are enforced by the runtime, not the prompt, so a successful prompt injection still
cannot escalate privilege. Every high-risk action requires human approval.

Found a vulnerability? Open a private security advisory rather than a public issue.

## License

To be determined before the first public release.
