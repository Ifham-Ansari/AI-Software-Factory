# 0004: Worktree layout and the integration worktree

**Status:** accepted · 2026-10-27

* Worktrees live at `<parent>/.asf-worktrees/<project-folder>/<agent>-<task>` (the design said `<project>/../.asf-worktrees/<agent>-<task>`; the extra project folder keeps two AI Software Factory projects in the same parent folder apart).
* A permanent worktree `_integration` holds the `asf/integration` branch. Planning runs (PM, designer, tech lead before the build) work there directly and their output is auto-committed; merges happen there, serialized.
* Local state (`asf.db`, runs, config, shims, scratch folders) is excluded through `.git/info/exclude`, so `asf init` never modifies the owner's branch. The integration branch also gets a `.gitignore` block for the scratch folders.
