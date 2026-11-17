# Contributing to AI Software Factory

Thanks for helping! AI Software Factory is small on purpose: plain code makes the decisions, and markdown skills describe agent behavior.

## Setup

```bash
corepack pnpm install && corepack pnpm build
```

Node 22.18+ runs the TypeScript directly, so the dashboard is the only thing that gets built.

| Command | What it runs |
|---|---|
| `pnpm check` | Typecheck, lint, and every Vitest suite (unit and end-to-end, with the fake `claude`) |
| `pnpm test` | Vitest only |
| `pnpm test:e2e` | Dashboard Playwright tests (builds the dashboard first) |
| `pnpm --filter @asf/dashboard dev` | Dashboard dev server, proxying to a running `asf up` |
| `pnpm --filter @asf/dashboard screenshots` | Regenerates `docs/screenshots/` from a scripted fake project |
| `pnpm asf <command>` | Runs the CLI from the repo without installing it |

## Where things are

| Path | What |
|---|---|
| `packages/core` | Pure logic with no I/O: plan validation, scheduler, permissions, guard, stream parsing, schema |
| `packages/server` | Fastify API, WebSocket bus, orchestrator, agent runner, prompts |
| `packages/cli` | The `asf` command: owner commands, agent commands, and the guard hook |
| `packages/dashboard` | React + Vite + Tailwind v4 dashboard |
| `packages/fake-claude` | The `claude` test double that acts out scenario files |
| `skills/` | Each role's playbook. This is the spec for agent behavior |
| `roles.yaml` | Role definitions, write paths, and the default stack |
| `tests/` | End-to-end tests of whole pipelines (`tests/helpers.ts` has the harness) |
| `docs/` | Architecture, integration notes, security review, and [decisions](docs/decisions/) |

## Ground rules

1. **No real Claude runs in tests.** Everything automated uses `packages/fake-claude`: set `ASF_CLAUDE_BIN` to its `src/main.ts`, and describe agent behavior in a scenario file (see `startHarness` in `tests/helpers.ts`).
2. **Test first** for core logic, permissions, the guard, and the scheduler. `packages/core` stays pure.
3. **Deterministic over clever.** No LLM calls for scheduling, permissions, plan validation, or merging.
4. **Skills are the spec.** If code and a skill disagree, change both together and add a record in `docs/decisions/`. The agent CLI spec is `skills/team-protocol/references/asf-cli.md`.
5. **Erasable TypeScript only:** no enums, no parameter properties, `import type` for types, and `.ts` import specifiers.
6. **Small conventional commits** (`feat:`, `fix:`, `docs:`, `test:`).

## Adding a role or a stack

1. Create `skills/<role>/SKILL.md`. Give it a trigger-style description and keep it under about 400 lines. Put longer material in `skills/<role>/references/` and templates in `skills/<role>/templates/`.
2. Add the role to `roles.yaml` with its write paths.
3. If the role needs new CLI permissions, update `packages/core/src/permissions.ts` and its tests.
4. Add a dashboard color for the role in `packages/dashboard/src/styles.css` (`--role-<name>`, light and dark).
5. Record the decision in `docs/decisions/`.

## Before you open a pull request

- [ ] `pnpm check` passes.
- [ ] Dashboard changes pass `pnpm test:e2e`, and screenshots are regenerated if the UI changed visibly.
- [ ] Skills and code still agree, and any behavior change has a decision record.
- [ ] Docs and the README are updated for anything a user would notice.

## Reporting security issues

Please open a private security advisory on GitHub instead of a public issue. [docs/security-review.md](docs/security-review.md) describes the threat model.
