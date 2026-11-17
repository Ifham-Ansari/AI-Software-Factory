# 0012: Rename to AI Software Factory (`asf`)

**Status:** accepted · 2026-11-17

**Context.** The owner renamed the project to **AI Software Factory**, asked for the previous name to be removed everywhere, and asked for a new logo and icons.

**Decision.**
* **Display name:** "AI Software Factory" in the README, docs, skills, dashboard, CLI messages, and guard messages (for example `AI Software Factory guard: …`).
* **Short identifier:** `asf`, used wherever a short name is needed:

  | What | Name |
  |---|---|
  | Command and launcher | `asf`, `packages/cli/bin/asf.js` |
  | Project folder and database | `<project>/.asf/`, `.asf/asf.db` |
  | Per-user state (registry, server info, Windows shim) | `~/.asf/` |
  | Environment variables | `ASF_*` (for example `ASF_TASK`, `ASF_CLAUDE_BIN`, `ASF_HOME`) |
  | Workspace packages | `@asf/core`, `@asf/server`, `@asf/cli`, `@asf/dashboard`, `@asf/fake-claude` |
  | Isolated mode | `asf/integration` branch, `../.asf-worktrees/` |
  | Agent CLI spec | `skills/team-protocol/references/asf-cli.md` |
  | Dashboard theme key | `asf.theme` |
  | Code identifiers | `AsfServer`, `AsfEvent`, `isAsf`, `asfHome` |

* **Brand:** a new mark (a factory with a line of three agents and an AI spark, on a blue `#3366FF` → violet `#8A3FFC` tile) and an outlined Inter ExtraBold wordmark. The dashboard accent moves to brand indigo (`#4338CA` light, `#A5B4FC` dark). See `docs/brand/README.md`.

**Consequences.**
* **No compatibility layer.** The code reads only the new names. A project created under the previous name is not recognized until its hidden project folder is renamed to `.asf/` (and the database files inside to `asf.db*`), or `asf init` is run in it again.
* Owners who installed the global command under the previous name should run `asf setup` once and remove the old command and PATH entry.
* The theme preference stored in the browser resets once.
