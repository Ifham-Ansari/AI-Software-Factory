# 0003: Skills live in `.asf/skills/` and are injected per role

**Status:** accepted · 2026-10-27

Claude Code auto-discovers `.claude/skills/` in the working directory and its parents, which would offer every agent every role's skills. `--disable-slash-commands` turns off all skills, and `--plugin-dir` would need a plugin per role.

**Decision.** `asf init` copies `skills/` to `.asf/skills/` on the integration branch (committed, so every worktree has them). For each run, the role's SKILL.md bodies (frontmatter stripped), in `roles.yaml` order with team-protocol first, are appended to the system prompt through `--append-system-prompt-file`. References and templates are opened on demand by path. The dashboard's skills editor edits and commits `.asf/skills/` on the integration branch, with reset-to-default.
