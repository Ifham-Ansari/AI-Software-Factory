# AI Software Factory documentation

Start with the [main README](../README.md) for what AI Software Factory is, how to install it, and a tour of the dashboard. The documents below go deeper.

## Using it

| Document | What's in it |
|---|---|
| [README: Quickstart](../README.md#quickstart) | Install, `asf setup`, `asf up` |
| [README: Your first build](../README.md#your-first-build) | A step-by-step first project, gate by gate |
| [Example ideas](../examples/README.md) | Idea briefs you can paste into the Idea screen |
| [Built-in engine](engine.md) | Run without a subscription: free API keys, local models, team keys, choosing models, making free limits last |
| [Security review](security-review.md) | What agents can and cannot do, controls, and known limits |

## How it works

| Document | What's in it |
|---|---|
| [Architecture](architecture.md) | Server, orchestrator, runner, CLI, and dashboard; where state lives; the run lifecycle |
| [Claude Code integration](claude-code-integration.md) | The exact `claude` flags, hooks, and stream format AI Software Factory relies on, and how each was verified |
| [Agent CLI reference](../skills/team-protocol/references/asf-cli.md) | Every `asf` command agents use, with permissions and exit codes |
| [Roles](../roles.yaml) | Role definitions, write paths, and the default stack |
| [Skills](../skills/) | Each role's playbook (the spec for agent behavior) |

## Decisions

Architecture decision records, oldest first. Each one states the context, the decision, and its consequences.

| # | Decision |
|---|---|
| [0001](decisions/0001-node-sqlite.md) | SQLite through Node's built-in `node:sqlite` instead of better-sqlite3 |
| [0002](decisions/0002-no-build-typescript.md) | Run TypeScript directly with Node type stripping |
| [0003](decisions/0003-skill-placement.md) | Skills live in `.asf/skills/` and are injected per role |
| [0004](decisions/0004-worktree-layout.md) | Worktree layout and the integration worktree (isolated mode) |
| [0005](decisions/0005-tasks-for-every-run.md) | Every agent run belongs to a task |
| [0006](decisions/0006-check-commands.md) | Integration check commands come from a `## Checks` section |
| [0007](decisions/0007-cli-exit-codes.md) | Exit code 1 for refusals |
| [0008](decisions/0008-change-requests-and-design-gate.md) | Change requests, a design gate, and existing codebases |
| [0009](decisions/0009-token-efficiency.md) | Keeping agent communication cheap |
| [0010](decisions/0010-direct-workspace.md) | Direct workspace mode is the default |
| [0011](decisions/0011-process-tracks.md) | Process tracks sized by triage |
| [0012](decisions/0012-rename-to-ai-software-factory.md) | Rename to AI Software Factory (`asf`) |
| [0013](decisions/0013-logged-out-claude-pauses.md) | A logged-out Claude Code pauses the team instead of failing tasks |
| [0014](decisions/0014-builtin-engine.md) | A built-in engine that runs agents on the team's own API keys |
| [0015](decisions/0015-models-by-task.md) | Choosing models by task, from every free provider |

## Project history

The [milestone plans](plan/) (M0 to M7) record how the first version was built.

## Brand

Logo, colors, and favicon files: [brand/](brand/README.md).
