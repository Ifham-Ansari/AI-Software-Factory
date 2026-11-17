# asf CLI reference

The `asf` CLI is the only way agents read and write shared team state. It talks to the local AI Software Factory server, which stores everything in `.asf/asf.db` and streams events to the dashboard. All commands print plain text by default; add `--json` for machine-readable output.

Environment variables set by the orchestrator for every agent run:

| Variable | Meaning |
|---|---|
| `ASF_AGENT` | Your agent ID, for example `backend-1` |
| `ASF_ROLE` | Your role, for example `backend` |
| `ASF_TASK` | The task you were started for, for example `T012` |
| `ASF_ROOT` | Path to the main project checkout (read only for you) |
| `ASF_WORKTREE` | Your worktree path |

## Identity and orientation

```bash
asf whoami
# agent: backend-1   role: backend
# task: T012 "Orders list endpoint with pagination"
# worktree: ../.asf-worktrees/backend-1-T012   branch: asf/T012-orders-list

asf task show T012          # full task: goal, context, criteria, owned paths, deps, review notes
asf task list --ready       # tasks ready to start (useful for leads only)
asf task list --role frontend --status in_progress
asf doc list                # PRD, architecture, contracts, design, decisions with paths
```

## Working a task

```bash
asf task start T012
asf progress "Schema and migration done; writing endpoint tests"
asf task block T012 --on @tech-lead --reason "Contract has no error shape for invalid cursor"
asf task unblock T012       # usually done for you when your question is answered
asf task done T012 --status DONE --handoff .asf/handoffs/T012.md
asf task done T012 --status DONE_WITH_CONCERNS --handoff .asf/handoffs/T012.md
asf task done T012 --status NEEDS_CONTEXT --handoff .asf/handoffs/T012.md   # lists missing information
# There is no BLOCKED status for `done`: a blocked task uses `asf task block`.
```

`asf task done` fails if your owned files have uncommitted changes, so commit first. Scratch folders (`.asf/handoffs/`, `.asf/reviews/`, `.asf/screens/`) are gitignored and excluded from this check; the CLI reads the file you pass and stores its content on the board. For `DONE` and `DONE_WITH_CONCERNS` it then runs the task's `verify` command in your worktree and refuses to complete the task on a non-zero exit, printing the output. Fix the failure and run it again.

## Messaging

Addresses: a role (`@pm`, `@tech-lead`, `@designer`, `@backend`, `@frontend`, `@qa`, `@reviewer`, `@devops`, `@security`), a specific agent (`@backend-2`), everyone (`@team`, use rarely), or the owner (`@human`).

```bash
asf msg @frontend "Auth cookie name is asf_session (httpOnly, SameSite=Lax). See D-004."
asf ask @pm "Can guests check out, or is login required? PRD section 4.2 does not say."
asf ask @human "Stripe test keys are needed for T020. Add STRIPE_SECRET_KEY to .env?"
asf inbox                   # unread messages, newest last
asf inbox --all             # full thread history for your task
asf reply M-0042 "Done, merged in T012."
```

`asf ask` blocks your task until someone replies. The reply arrives in your inbox, and the orchestrator resumes you with it in your prompt. Ask one clear question per `ask`, include where you looked, and propose a default: "I suggest X because Y; OK?" Questions with a proposed default get answered faster.

For several decisions at once (the PM's discovery questions, the designer's visual directions), send one batch so the owner answers everything in a single sitting:

```bash
asf ask @human --batch .asf/docs/discovery/questions.json
```

The dashboard shows each question as a card with options and your recommendation, and an "accept all recommendations" button. The batch file format is in the product-manager skill (`references/discovery.md`).

## Decisions (lightweight ADRs)

```bash
asf decision "Cursor pagination for all list endpoints" \
  --why "Offset pagination breaks with concurrent inserts; lists are append heavy" \
  --affects backend,frontend
asf decision list
asf decision show D-007
```

Decisions are stored in `.asf/docs/decisions/` and shown on the dashboard. Record a decision when the choice constrains other agents or will surprise a future reader.

## Lessons (project memory)

```bash
asf lesson "Use the shared <Dialog>, never window.confirm" --paths "frontend/src/**" --roles frontend
asf lesson "Run alembic upgrade before backend tests or they fail with missing tables" --paths "backend/**"
```

One rule per lesson, under 300 characters. Record a lesson when you hit (or had to fix) a mistake that a teammate is likely to make again: a project convention, a trap in the tooling, a fix that worked. Lessons are shown to every later run whose role and files match, so they save the next agent a review round. Do not record task-specific facts; those go in your handoff.

## Documents

```bash
asf doc show prd
asf doc show contracts/openapi.yaml
asf doc submit prd --file .asf/docs/prd.md      # PM / tech lead / designer: submit for human approval
asf doc submit architecture                      # --file is optional when the doc lives at its standard path
```

Document names and their standard paths (used by `doc show` and `doc submit` when `--file` is omitted):

| Name | Path | Owner |
|---|---|---|
| `prd` | `.asf/docs/prd.md` | PM |
| `architecture` | `.asf/docs/architecture.md` | Tech lead |
| `contracts/<file>` | `.asf/docs/contracts/<file>` (for example `contracts/openapi.yaml`) | Tech lead (design tokens: designer) |
| `design` | `.asf/docs/design/DESIGN.md` plus `.asf/docs/design/screens/` | Designer |
| `plan` | `.asf/docs/plan-summary.md` plus the task files in `.asf/tasks/` | Tech lead |
| `decisions/<id>` | `.asf/docs/decisions/<id>.md` | Whoever recorded it |

Documents submitted for approval appear in the dashboard's approval queue. Work that depends on an unapproved document stays `todo`.

## Planning (tech lead)

```bash
asf plan submit .asf/tasks/       # import task files into the board
asf plan check .asf/tasks/        # same validation without importing
```

Validation is deterministic and checks: required fields present, every `after` ID exists, no dependency cycles, and no ownership collisions (two tasks with no dependency path between them whose `owns` globs overlap). It prints each problem with the task IDs involved. The plan is not imported until it passes, and build tasks stay `todo` until the owner approves the plan in the dashboard.

## Review and QA (reviewer, QA, and designer roles)

The designer uses the same review commands for design review of built UI tasks; QA uses the `qa` commands.

```bash
asf review start T012
asf review comment T012 --file app/api/orders.py --line 42 --severity major "Cursor is not validated; invalid base64 raises 500"
asf review approve T012 --summary "Clean; one minor nit left as comment"
asf review request-changes T012 --summary "2 major issues, see comments" --file .asf/reviews/T012.md   # --file attaches the full review

asf qa pass T012 --report .asf/reviews/T012-qa.md
asf qa fail T012 --report .asf/reviews/T012-qa.md          # creates bug items linked to the task
asf bug create --task T012 --severity major --title "..." --file .asf/reviews/T012-bug-1.md   # severity: blocker | major | minor | trivial
```

## Exit codes

`0` success, `1` refused on its merits (for example `task done` with uncommitted owned files or a failing `verify`, or a plan with problems; read the output and fix your work), `2` invalid arguments, `3` not allowed for your role or task, `4` server unreachable. If the server is unreachable, wait a few seconds and retry once; if it still fails, finish your local work, commit, and leave the handoff note at `.asf/handoffs/<task>.md`; the orchestrator collects it when the server is back.
