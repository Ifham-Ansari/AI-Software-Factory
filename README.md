# AI Software Factory

A hierarchical, supervised autonomous software engineering and deployment system. Describe an
application in natural language; an organization of AI agents plans it, builds it, tests it, deploys
it, and hands you live URLs — escalating every high-risk decision to a human.

> ## Status: Phase 1 complete — platform foundation
>
> Registration, sign-in, rotating refresh tokens with theft detection, per-owner project
> CRUD, an audit trail, structured logging with secret redaction, generated TypeScript
> contracts, and a Next.js control centre. **No AI agents yet** — those start in Phase 3.
>
> 313 backend tests · 32 frontend tests · 10 end-to-end specs.
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

For Phase 1, that is all you need:

- Python 3.13 and [uv](https://docs.astral.sh/uv/) — uv installs the right Python for you
- Node 22+ and pnpm
- A PostgreSQL database — a [Neon](https://neon.com) project, or Docker locally

Later phases add more: Upstash Redis (Phase 2), OpenAI and LangSmith (Phase 3), Docker for
the code sandbox (Phase 5), GitHub/Vercel/Render tokens (Phases 5 and 7). None is needed
to run what exists today.

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

Two variables are required today:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string. A plain `postgresql://` URL is rewritten to the psycopg driver automatically, so a pasted Neon string works unmodified |
| `JWT_SECRET_KEY` | Signs access tokens. At least 32 characters; startup refuses anything shorter |

Generate a signing key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Everything else has a working default — see [.env.example](.env.example), which documents
each one and what it does.

The frontend needs `API_BASE_URL` in `apps/web/.env.local` if the API is not on
`http://127.0.0.1:8000`. It is deliberately **not** a `NEXT_PUBLIC_` variable: the browser
never calls the API directly, so nothing about the backend's location reaches the bundle.

⚠️ **Never put a real secret in `.env.example`.** It is committed. Real values belong in
`.env`, which is gitignored.

### Database

```bash
uv run alembic upgrade head
```

### Run

Three processes, one terminal each:

```bash
uv run dev-api               # FastAPI      → http://127.0.0.1:8000  (docs at /docs)
uv run dev-worker            # workflow worker (a process shell until Phase 2)
pnpm --filter web dev        # Next.js      → http://127.0.0.1:3000
```

Then open http://127.0.0.1:3000 and register an account.

> **On Windows, start the backend with `uv run dev-api`, not `uvicorn` directly.**
> psycopg's async mode cannot use Windows' default `ProactorEventLoop`, and uvicorn selects
> its loop through a factory that ignores the asyncio policy. `dev-api` owns the loop and
> picks a compatible one; invoking uvicorn yourself produces an `InterfaceError` on the
> first query that reads like a connectivity problem. Linux is unaffected.

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

```bash
docker run -d --name factory-test-db -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:17-alpine
export TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres
uv run pytest -m integration
```

CI provisions this automatically; see [.github/workflows/ci.yml](.github/workflows/ci.yml).

### Quality gates

```bash
uv run ruff check . && uv run mypy --strict && uv run lint-imports
pnpm --filter web lint && pnpm --filter web exec tsc --noEmit
```

`lint-imports` enforces the layering rules — `core` may not import LangGraph or FastAPI, `agents`
may not import FastAPI. A violation fails the build.

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
Read docs → inspect code → design → implement → TEST → fix → verify criteria → document → commit
```

Phases are built strictly in order, and a phase is complete only when its acceptance criteria have
passing tests — not when the code compiles. Full procedure in [instructions.md](instructions.md).

Two rules that matter more than the rest: **after implementing anything, test it before moving on**,
and **no source file exceeds 250 lines** (enforced in CI).

## Roadmap

| Phase | Delivers | Status |
|---|---|---|
| 1 | Platform foundation, auth, projects, contracts, CI | **Complete** |
| 2 | Secret vault, event bus, WebSocket, job queue | Not started |
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
