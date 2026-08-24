# Feature Registry — AI Software Factory

> **Phase 1 is complete: all 18 features `VERIFIED`. Phases 2-8 remain `PLANNED`.**
> This registry is the single source of truth for what exists. It is updated during a phase, not
> after it. See [instructions.md](instructions.md) §4 for the update protocol.

---

## How to read this file

**Statuses**

| Status | Meaning |
|---|---|
| `PLANNED` | Designed, not started |
| `IN_PROGRESS` | Being implemented right now |
| `IMPLEMENTED` | Code written, tests not yet passing or not yet written |
| `TESTING` | Tests written and running; failures being resolved |
| `VERIFIED` | All tests pass **and** acceptance criteria demonstrably met |
| `BLOCKED` | Cannot proceed; blocker recorded in the Notes column |
| `DEPRECATED` | Removed or superseded; superseding feature ID recorded |

**The one rule that matters:** `VERIFIED` requires a passing test you can point at. "It works when I
try it" is `IMPLEMENTED`, not `VERIFIED`. A feature that regresses drops back to `TESTING`.

**ID scheme.** `F-<phase><nn>` — e.g. `F-304` is the fourth feature of Phase 3. IDs are permanent;
deprecated IDs are never reused.

**Paths** are the intended implementation location. When implementation lands somewhere else, the
registry is corrected — the registry follows the code, not the other way around.

---

## Phase 1 — Platform Foundation & Contracts

> **Phase 1 verification status.** All 18 features are `VERIFIED` — every one has a test
> that ran and passed, against real infrastructure:
>
> | Suite | Count | Environment |
> |---|---|---|
> | Backend (unit, integration, security, failure) | 393 | Real PostgreSQL (Neon), 0 skipped |
> | Frontend component and validation | 40 | jsdom |
> | End-to-end (Playwright) | 12 | Full stack: Next.js + FastAPI + PostgreSQL |
>
> Backend coverage is 91% on `packages/core` against a gate of 85%.
>
> The integration suite runs against a dedicated throwaway database, never the application
> one. See [README.md](README.md#test) for how to point it at yours.

| ID | Feature | Status | Depends | Location | Tests | Acceptance |
|---|---|---|---|---|---|---|
| F-101 | Monorepo & toolchain (uv + pnpm workspaces, ruff, mypy strict, import-linter, ESLint) | VERIFIED | — | repo root, `pyproject.toml`, `pnpm-workspace.yaml` | CI lint/type jobs | Clean clone installs and lints on Windows and Linux |
| F-102 | Layered configuration (Pydantic Settings, env layering, PUBLIC/SECRET split) | VERIFIED | F-101 | `packages/core/config/` | unit | Missing required var aborts startup naming the variable |
| F-103 | Async persistence layer (psycopg3 engine, session, unit of work) | VERIFIED | F-102 | `packages/core/persistence/` | unit + integration | Session commits/rolls back correctly under concurrency |
| F-104 | Alembic migrations | VERIFIED | F-103 | `packages/core/migrations/` | integration | `upgrade head` and `downgrade base` both succeed clean |
| F-105 | Scoped repository pattern | VERIFIED | F-103 | `packages/core/persistence/repositories/` | unit + integration | Repository cannot be constructed without a scope |
| F-106 | User registration, email OTP verification & Argon2id hashing | VERIFIED | F-105 | `packages/core/security/`, `packages/core/application/auth/verification.py`, `apps/api/routers/auth.py` | unit + integration + security | Duplicate email rejected; hash never returned; sign-in refused until the emailed code is redeemed; code never logged, returned, or reusable |
| F-107 | JWT access + rotating refresh tokens with reuse detection | VERIFIED | F-106 | `packages/core/security/tokens.py` | unit + integration + failure | Reused refresh token revokes the whole family |
| F-108 | Authorization guard & project ownership | VERIFIED | F-107 | `apps/api/dependencies/` | integration + failure | Cross-user access returns 404, not 403 |
| F-109 | Audit log writer | VERIFIED | F-108 | `packages/core/domain/audit/` | integration | Every mutating action writes an attributable row |
| F-110 | Project CRUD | VERIFIED | F-108 | `packages/core/application/projects/` | unit + integration + e2e | Full lifecycle works and is owner-scoped |
| F-111 | API error envelope & stable error codes | VERIFIED | F-102 | `apps/api/errors.py` | unit + failure | No unhandled exception leaks a stack trace |
| F-112 | Request-ID correlation middleware | VERIFIED | F-111 | `apps/api/middleware/` | integration | Every log line in a request carries its request ID |
| F-113 | Pagination, filtering, sorting | VERIFIED | F-110 | `apps/api/schemas/common.py` | unit + integration | Stable ordering; invalid params rejected |
| F-114 | Health & readiness endpoints | VERIFIED | F-103 | `apps/api/routers/health.py` | integration + failure | `/ready` reports per-dependency status |
| F-115 | Structured logging & redaction filter | VERIFIED | F-102 | `packages/core/observability/` | unit + failure | Planted secret never appears in output |
| F-116 | OpenAPI → TypeScript contract generation | VERIFIED | F-110 | `packages/contracts/`, `scripts/` | contract | CI fails on generated-type drift |
| F-117 | Next.js app shell, auth pages, project UI | VERIFIED | F-116 | `apps/web/` | component + e2e | Register → create project works in a browser |
| F-118 | CI pipeline with coverage & file-size gates | VERIFIED | F-101 | `.github/workflows/` | — | Build fails on any source file over 250 lines |

## Phase 2 — Secure Configuration, Secrets & Realtime Backbone

| ID | Feature | Status | Depends | Location | Tests | Acceptance |
|---|---|---|---|---|---|---|
| F-201 | Envelope encryption (KEK → per-project DEK → AES-256-GCM) | PLANNED | F-103 | `packages/core/security/envelope.py` | unit + failure | Wrong DEK fails closed; rotation preserves access |
| F-202 | Secret vault with write-only API | PLANNED | F-201 | `packages/core/application/secrets/` | unit + integration + failure | **No endpoint returns a secret value** |
| F-203 | `secret://` reference format & resolver with sink allowlist | PLANNED | F-202 | `packages/core/security/references.py` | unit + failure | Resolution from a disallowed sink raises |
| F-204 | Secret access audit log | PLANNED | F-203 | `packages/core/domain/secrets/` | integration | Every resolution is attributable to actor and purpose |
| F-205 | `SecretRedactor` (known values + high-entropy patterns) | PLANNED | F-202 | `packages/core/security/redaction.py` | unit + failure | Redacts across logs, errors, and nested structures |
| F-206 | Config requirement catalog & satisfaction tracking | PLANNED | F-202 | `packages/core/domain/config/` | unit + integration | Project reports exactly which credentials are missing |
| F-207 | Redis client, rate limiting, idempotency store, distributed lock | PLANNED | F-102 | `packages/core/infrastructure/redis/` | unit + integration + failure | Limits return 429 with `Retry-After`; locks expire safely |
| F-208 | Event model (envelope + discriminated payload union) | PLANNED | F-103 | `packages/core/events/schemas/` | unit | Unknown event type rejected at the boundary |
| F-209 | Event store with per-run sequence numbers | PLANNED | F-208 | `packages/core/events/store.py` | integration | `seq` is gapless and unique per run under concurrency |
| F-210 | Persist-then-publish event publisher | PLANNED | F-209, F-207 | `packages/core/events/publisher.py` | integration + failure | Redis down → events still persisted, run unaffected |
| F-211 | WebSocket endpoint with ticket auth & fan-out | PLANNED | F-210 | `apps/api/ws/` | integration + e2e + failure | Two API replicas both deliver a published event |
| F-212 | Event replay from sequence number | PLANNED | F-209 | `apps/api/routers/events.py` | integration + e2e | Reconnect after 30s outage loses nothing, duplicates nothing |
| F-213 | Durable job queue (SKIP LOCKED, leases, backoff, dead-letter) | PLANNED | F-103 | `packages/core/infrastructure/queue/` | unit + integration + failure | Concurrent workers each claim a job exactly once |
| F-214 | Worker process (claim loop, handler registry, graceful drain) | PLANNED | F-213 | `apps/worker/` | integration + failure | SIGTERM drains in-flight work without loss |
| F-215 | Frontend realtime client (reconnect, replay, event store) | PLANNED | F-211 | `apps/web/src/lib/ws/` | component + e2e | Connection status is visible and accurate |
| F-216 | Key management runbook | PLANNED | F-201 | `docs/runbooks/key-management.md` | — | Rotation procedure executed successfully once |

## Phase 3 — Agent Runtime & Intake

| ID | Feature | Status | Depends | Location | Tests | Acceptance |
|---|---|---|---|---|---|---|
| F-301 | `ModelRegistry` (role → tier → model) & `ModelProvider` port | PLANNED | F-102 | `packages/agents/runtime/models/` | unit + failure | Model IDs are configuration, never literals in agent code |
| F-302 | Versioned prompt registry (`prompts/<agent>/vN.md`) | PLANNED | F-301 | `packages/agents/prompts/`, `runtime/prompts.py` | unit | Prompt version recorded on every call |
| F-303 | Structured output with validation and one repair attempt | PLANNED | F-301 | `packages/agents/runtime/structured.py` | unit + failure | Two malformed responses produce a typed failure, not a crash |
| F-304 | `RunBudget` & `BudgetGuard` on every model and tool call | PLANNED | F-301 | `packages/agents/runtime/budget.py` | unit + integration + failure | 80% warns, 100% interrupts to a human |
| F-305 | `FactoryTool` framework (schemas, risk, permissions, timeout, retry) | PLANNED | F-303 | `packages/agents/tools/base.py` | unit + failure | Tool outside `allowed_tools` is refused and audited |
| F-306 | Tool registry & invocation audit | PLANNED | F-305 | `packages/agents/tools/registry.py` | integration | Every invocation recorded with risk level and outcome |
| F-307 | LangSmith tracing with redaction hooks | PLANNED | F-205, F-301 | `packages/agents/runtime/tracing.py` | integration + failure | **No secret value appears in any trace payload** |
| F-308 | Run lifecycle (`workflow_runs`, `tasks`, `agent_executions`) | PLANNED | F-213 | `packages/core/domain/runs/` | unit + integration | Run state and checkpoint never disagree after a crash |
| F-309 | Postgres checkpointer on the `langgraph` schema | PLANNED | F-308 | `packages/agents/runtime/checkpointer.py` | integration + failure | Run resumes in a different worker process |
| F-310 | HITL primitive (`human_gate` node, approval records, resume endpoint) | PLANNED | F-309 | `packages/agents/graphs/nodes/human_gate.py` | integration + e2e + failure | Paused run holds no process open |
| F-311 | Interrupt re-execution safety (idempotent pre-interrupt side effects) | PLANNED | F-310 | `packages/agents/graphs/` | failure/regression | Resume produces **no** duplicate side effects |
| F-312 | Requirements Analyst agent | PLANNED | F-303 | `packages/agents/workers/requirements/` | unit + integration | Vague request yields specific, relevant gaps |
| F-313 | Intake subgraph (analyze → gaps → questions → interrupt → validate → spec) | PLANNED | F-312, F-310 | `packages/agents/graphs/intake/` | integration + e2e | Full pause/resume cycle completes |
| F-314 | Versioned `ProjectSpecification` | PLANNED | F-313 | `packages/core/domain/specs/` | unit + integration | Specs are immutable; changes create a new version |
| F-315 | Project chat & conversation history | PLANNED | F-110 | `packages/core/application/chat/` | integration + e2e | Multi-turn refinement carries context |
| F-316 | Frontend: chat, dynamic question form, spec review, run timeline | PLANNED | F-313, F-215 | `apps/web/src/features/intake/` | component + e2e | Questions render from the agent's structured output |
| F-317 | Token & cost accounting per run | PLANNED | F-304 | `packages/core/domain/usage/` | integration | Cost is attributable to run, task, and agent |

## Phase 4 — Hierarchical Supervision & Orchestration

| ID | Feature | Status | Depends | Location | Tests | Acceptance |
|---|---|---|---|---|---|---|
| F-401 | `AgentSpec` framework with import-time validation | PLANNED | F-305 | `packages/agents/runtime/spec.py` | unit | An agent missing a required field fails the build |
| F-402 | Delegation contracts (`TaskAssignment` / `TaskResult`) | PLANNED | F-401 | `packages/agents/state/contracts.py` | unit | Free-text delegation is impossible by type |
| F-403 | Task graph with dependencies & cycle detection | PLANNED | F-402 | `packages/core/domain/tasks/` | unit + failure | A dependency cycle is rejected at plan time |
| F-404 | Uniform supervisor base graph (plan/dispatch/collect/validate/complete) | PLANNED | F-403 | `packages/agents/supervisors/base.py` | unit + integration | All four departments reuse one implementation |
| F-405 | Executive Supervisor & deterministic phase router | PLANNED | F-404 | `packages/agents/supervisors/executive/` | unit + integration | Routing is deterministic except on genuine ambiguity |
| F-406 | Product, Engineering, Quality, Delivery supervisors | PLANNED | F-404 | `packages/agents/supervisors/` | integration | Each validates results against acceptance criteria |
| F-407 | Parallel dispatch via `Send` with merge reducers | PLANNED | F-404 | `packages/agents/graphs/parallel.py` | unit + integration | Independent tasks demonstrably overlap in time |
| F-408 | Error taxonomy & deterministic classifier | PLANNED | F-111 | `packages/core/errors/` | unit | Each class routes to its documented handling |
| F-409 | Retry policies with jittered exponential backoff | PLANNED | F-408 | `packages/agents/runtime/retry.py` | unit + failure | Retries carry `prior_failures` |
| F-410 | Circuit breakers on external dependencies | PLANNED | F-408 | `packages/core/infrastructure/resilience/` | unit + failure | Open breaker escalates instead of hammering |
| F-411 | Failure Analyst & recovery subgraph | PLANNED | F-408 | `packages/agents/graphs/recovery/` | integration + failure | Diagnosis carries a confidence score |
| F-412 | Escalation ladder (worker → supervisor → executive → human) | PLANNED | F-411 | `packages/agents/supervisors/escalation.py` | integration + failure | Every level is exercised by test |
| F-413 | Decision Arbiter & arbitration subgraph | PLANNED | F-406 | `packages/agents/graphs/arbitration/` | integration | Conflicting proposals yield a rationale and confidence |
| F-414 | Loop guards (visit count, recursion, wall-clock, budget) | PLANNED | F-405 | `packages/agents/runtime/guards.py` | failure | **No scripted failure pattern loops forever** |
| F-415 | Architect agent (architecture doc, data model, OpenAPI contract) | PLANNED | F-406 | `packages/agents/workers/architect/` | integration + e2e | Emits a valid OpenAPI document |
| F-416 | Research agent with SSRF-safe search/fetch and 24h cache | PLANNED | F-207 | `packages/agents/workers/research/`, `tools/web/` | unit + integration + failure | Private-range URLs rejected after DNS resolution |
| F-417 | Frontend: agent hierarchy tree, task board, decision log, escalations | PLANNED | F-215 | `apps/web/src/features/runs/` | component + e2e | Live view of who is doing what, under whom |

## Phase 5 — Workspace, Code Generation & Version Control

| ID | Feature | Status | Depends | Location | Tests | Acceptance |
|---|---|---|---|---|---|---|
| F-501 | `Workspace` port & hardened `ContainerWorkspace` | PLANNED | F-305 | `packages/core/infrastructure/workspace/` | integration + security | Egress denied by default; non-root; resource-capped |
| F-502 | Path-confined file tools | PLANNED | F-501 | `packages/agents/tools/files/` | unit + security | Traversal via `../`, absolute, symlink, unicode all rejected |
| F-503 | Allowlisted command runner (no shell, no chaining) | PLANNED | F-501 | `packages/agents/tools/commands/` | unit + security | Injection attempts rejected structurally |
| F-504 | Deterministic project scaffolds (FastAPI, Next.js) | PLANNED | F-502 | `packages/agents/scaffolds/` | golden-file | Scaffolded project type-checks before any LLM code |
| F-505 | Database Engineer agent | PLANNED | F-415 | `packages/agents/workers/database/` | integration | Models carry indexes, constraints, relationships |
| F-506 | Backend Engineer agent | PLANNED | F-415 | `packages/agents/workers/backend/` | integration + e2e | Implements the contract; emits `EnvContract` |
| F-507 | Frontend Engineer agent | PLANNED | F-415 | `packages/agents/workers/frontend/` | integration + e2e | Implements the contract; emits `EnvContract` |
| F-508 | Contract conformance checker (deterministic) | PLANNED | F-506, F-507 | `packages/core/domain/contracts/` | unit + integration | Detects an intentionally mismatched route |
| F-509 | Environment assembly from `EnvContract`s | PLANNED | F-508 | `packages/core/application/environments/` | unit | Conflicting declarations are detected, not merged silently |
| F-510 | Code Reviewer agent (incl. 250-line rule on generated code) | PLANNED | F-506 | `packages/agents/workers/reviewer/` | integration | Findings route back and the fix lands |
| F-511 | `VcsProvider` port & GitHub adapter | PLANNED | F-202 | `packages/core/infrastructure/providers/github/` | integration (fixtures) | Token resolved from vault, never in a prompt |
| F-512 | Git Agent (branching, task-linked conventional commits, push, PRs) | PLANNED | F-511 | `packages/agents/workers/git/` | integration + e2e | History is meaningful and traceable to tasks |
| F-513 | Artifact storage & diffing | PLANNED | F-502 | `packages/core/domain/artifacts/` | unit + integration | Checkpoints stay small; artifacts addressed by digest |
| F-514 | Frontend: file tree, diff viewer, commit history | PLANNED | F-513 | `apps/web/src/features/code/` | component + e2e | Generated code is reviewable in the UI |
| F-515 | Sandbox escape test suite | PLANNED | F-501 | `packages/core/tests/security/` | security | Traversal, fork bomb, OOM, egress, timeout all contained |

## Phase 6 — Verification, Security Review & Autonomous Recovery

| ID | Feature | Status | Depends | Location | Tests | Acceptance |
|---|---|---|---|---|---|---|
| F-601 | Test Engineer agent | PLANNED | F-506 | `packages/agents/workers/test_engineer/` | integration + e2e | Generated tests execute and are meaningful |
| F-602 | Deterministic test runners with structured result parsing | PLANNED | F-503 | `packages/agents/tools/testing/` | unit + failure | Pass/fail/error/skip parsed, not scraped from logs |
| F-603 | Static analysis runners (ruff, mypy, tsc, ESLint) | PLANNED | F-602 | `packages/agents/tools/analysis/` | unit + integration | Findings normalized to one schema |
| F-604 | Dependency audit & secret scanning of generated code | PLANNED | F-603 | `packages/agents/tools/security/` | integration | A planted credential is found |
| F-605 | Security Reviewer agent with hard-block authority | PLANNED | F-604 | `packages/agents/workers/security/` | integration + failure | **No agent can override a security block** |
| F-606 | Quality Supervisor gate (aggregated report, binary verdict, no bypass) | PLANNED | F-605 | `packages/agents/supervisors/quality/` | integration + failure | Gate bypass attempt fails by test |
| F-607 | Autonomous failure→fix loop with attempt budget | PLANNED | F-411, F-602 | `packages/agents/graphs/quality/` | integration + failure | Known bug fixed autonomously; unfixable bug escalates |
| F-608 | Regression protection (full re-run after any fix) | PLANNED | F-607 | `packages/agents/supervisors/quality/` | integration | A fix that breaks another test is caught |
| F-609 | Oscillation detection (fix A breaks B breaks A) | PLANNED | F-607 | `packages/agents/runtime/guards.py` | failure | Thrashing escalates rather than continuing |
| F-610 | Flaky-test quarantine & reporting | PLANNED | F-602 | `packages/agents/tools/testing/` | integration | Flakes are reported, never silently retried to green |
| F-611 | Generated-app integration testing against an ephemeral database | PLANNED | F-601 | `packages/agents/tools/testing/` | integration | Backend + DB verified together |
| F-612 | Frontend: test results, coverage, findings, live fix-loop view | PLANNED | F-215 | `apps/web/src/features/quality/` | component + e2e | The fix loop is watchable in real time |

## Phase 7 — Database Provisioning, Migrations & Deployment

| ID | Feature | Status | Depends | Location | Tests | Acceptance |
|---|---|---|---|---|---|---|
| F-701 | `DatabaseProvider` port & Neon adapter | PLANNED | F-202 | `packages/core/infrastructure/providers/neon/` | integration (fixtures) | Connection string lands in the vault, never in state |
| F-702 | Per-project environments (dev/staging/production) | PLANNED | F-701 | `packages/core/domain/environments/` | unit + integration | Credentials are per-environment |
| F-703 | Destructive-operation static analysis | PLANNED | F-505 | `packages/core/domain/migrations/analysis.py` | unit | DROP, TRUNCATE, narrowing ALTER, NOT NULL-on-populated detected |
| F-704 | Migration dry-run on an ephemeral Neon branch | PLANNED | F-701, F-703 | `packages/core/application/migrations/` | integration | A bad migration is caught before touching the target |
| F-705 | Neon branch lifecycle & reaper | PLANNED | F-704 | `packages/core/infrastructure/providers/neon/` | integration | No orphaned branches after a failed run |
| F-706 | Full migration pipeline (generate→validate→dry-run→approve→apply→verify) | PLANNED | F-704, F-310 | `packages/agents/graphs/delivery/migration/` | integration + e2e + failure | Destructive migration requires approval, always |
| F-707 | `DeploymentProvider` port | PLANNED | F-202 | `packages/core/infrastructure/providers/base.py` | unit | Adding a provider requires no supervisor changes |
| F-708 | Vercel adapter (frontend) | PLANNED | F-707 | `.../providers/vercel/` | integration (fixtures) | Deploy, status, logs, rollback all covered |
| F-709 | Render adapter (backend) | PLANNED | F-707 | `.../providers/render/` | integration (fixtures) | Deploy, status, logs, rollback all covered |
| F-710 | Deployment Agent with ordered orchestration & idempotency keys | PLANNED | F-708, F-709 | `packages/agents/workers/deployment/` | integration + failure | Interrupt-resume never double-deploys |
| F-711 | Secret injection into provider environments | PLANNED | F-203, F-710 | `packages/core/application/deployments/` | integration + failure | Values pass vault→provider without entering state or traces |
| F-712 | Health verification (deterministic probes) | PLANNED | F-710 | `packages/core/application/health/` | integration + failure | Unhealthy deploy triggers rollback |
| F-713 | Deployment failure recovery from real build logs | PLANNED | F-411, F-710 | `packages/agents/graphs/delivery/recovery/` | integration + e2e | Log-driven fix succeeds at least once in e2e |
| F-714 | Rollback (deployment restore + safe migration down) | PLANNED | F-712 | `packages/core/application/deployments/` | integration + failure | Rollback restores a working state |
| F-715 | Approval gates on all HIGH/DESTRUCTIVE actions | PLANNED | F-310 | `packages/core/domain/policies/risk.py` | integration + failure | An agent can raise risk but never lower it |
| F-716 | Credential-free delivery report | PLANNED | F-712 | `packages/core/application/reports/` | unit + failure | Report scanned against the vault contains no value |
| F-717 | Frontend: pipeline view, approval modals, live build logs, report page | PLANNED | F-215 | `apps/web/src/features/delivery/` | component + e2e | Approval modal shows enough context to decide |

## Phase 8 — Evaluation, Knowledge & Production Hardening

| ID | Feature | Status | Depends | Location | Tests | Acceptance |
|---|---|---|---|---|---|---|
| F-801 | LangSmith evaluation datasets (50+ scenarios) | PLANNED | F-307 | `docs/evaluation/datasets/` | — | Expectations derived from spec, not observed output |
| F-802 | Agent evaluators (intake, routing, tool selection, plan quality) | PLANNED | F-801 | `packages/agents/evaluation/` | integration | Scores are reproducible |
| F-803 | Supervisor evaluators (delegation, retry, escalation correctness) | PLANNED | F-801 | `packages/agents/evaluation/` | integration | Supervision quality is measured, not asserted |
| F-804 | Evaluation regression gate in CI | PLANNED | F-802 | `.github/workflows/` | — | A quality drop blocks the merge |
| F-805 | Engineering standards corpus (pgvector) | PLANNED | F-104 | `packages/core/infrastructure/knowledge/` | integration | Retrieval measurably changes generated output |
| F-806 | Policy-aware generation (retrieve before generate, cite in output) | PLANNED | F-805 | `packages/agents/runtime/knowledge.py` | integration | Agents cite the standard they applied |
| F-807 | Per-project & per-user quotas | PLANNED | F-317 | `packages/core/domain/quotas/` | unit + integration + failure | Exhaustion blocks new runs with a clear message |
| F-808 | Cost dashboard & budget alerts | PLANNED | F-807 | `apps/web/src/features/usage/` | component + e2e | Cost per run is visible and attributable |
| F-809 | OpenTelemetry metrics, traces & SLOs | PLANNED | F-115 | `packages/core/observability/` | integration | A run is traceable frontend→provider |
| F-810 | Alert rules & dependency health dashboard | PLANNED | F-809 | `infra/`, `apps/web/` | integration | Every alert has a runbook |
| F-811 | Platform security review (authz matrix, SSRF/injection suite, threat model) | PLANNED | F-108 | `packages/core/tests/security/`, `docs/` | security | Full authz matrix passes |
| F-812 | Load & soak testing, pool tuning, degradation matrix | PLANNED | F-809 | `tests/load/` | load | 10× expected concurrency sustained |
| F-813 | Backup, restore & disaster-recovery drill | PLANNED | F-104 | `docs/runbooks/` | integration | Restore verified end to end |
| F-814 | Operational runbooks | PLANNED | F-810 | `docs/runbooks/` | — | Key rotation, stuck run, provider outage, cost spike, incident |
| F-815 | Documentation rewrite against the shipped system | PLANNED | all | root `*.md` | — | All six documents describe what exists |

---

## Registry summary

| Phase | Features | VERIFIED | Status |
|---|---|---|---|
| 1 — Platform Foundation | 18 | 18 | **COMPLETE** |
| 2 — Secrets & Realtime | 16 | 0 | NOT STARTED |
| 3 — Agent Runtime & Intake | 17 | 0 | NOT STARTED |
| 4 — Hierarchical Supervision | 17 | 0 | NOT STARTED |
| 5 — Workspace & Code Gen | 15 | 0 | NOT STARTED |
| 6 — Verification & Recovery | 12 | 0 | NOT STARTED |
| 7 — Database & Deployment | 17 | 0 | NOT STARTED |
| 8 — Evaluation & Hardening | 15 | 0 | NOT STARTED |
| **Total** | **127** | **18** | **Phase 1 complete** |

---

## Deprecated features

*None yet.* When a feature is removed or superseded, move its row here with a `DEPRECATED` status,
the date, and the superseding ID. Never delete a row and never reuse an ID.

---

## Change log

| Date | Change |
|---|---|
| 2026-08-23 | Registry created. 127 features across 8 phases, all `PLANNED`. |
| 2026-08-23 | Phase 1 implemented. 14 features `VERIFIED`; F-103/104/105/109 `TESTING` pending a database. |
| 2026-08-23 | Integration and e2e suites executed against real infrastructure. All 18 Phase 1 features `VERIFIED`. |
