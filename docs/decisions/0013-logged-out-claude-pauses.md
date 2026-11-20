# 0013: A logged-out Claude Code pauses the team

**Status:** accepted · 2026-11-20

**Context.** When the `claude` CLI had no usable login (an expired OAuth session, or never logged in), every agent run ended within a second with "Failed to authenticate: OAuth session expired and could not be refreshed" or "Not logged in · Please run /login". The orchestrator treated each one as an ordinary failed run. After three of them the task was blocked, and the owner saw only "P-001 is blocked · run failed". The real cause was visible only in `.asf/runs/<run>/stream.jsonl`. Unblocking the task failed the same way, because nothing had changed.

**Decision.** The stream parser recognizes a login failure in two ways. One is the synthetic assistant message Claude Code tags `error: "authentication_failed"`. The other is an error result whose text starts with `Not logged in`, `Invalid API key`, `Failed to authenticate`, `OAuth token has expired` or `Please run /login`, or contains the API's 401 `authentication_error`. The pattern is anchored at the start so an agent's own words about a `/login` page never match. Such a run ends with status `auth_failed`, and then the orchestrator:

* pauses the scheduler with the reason "Claude Code is not logged in" (shown in the header and on Needs you, with a Resume button);
* raises one alert telling the owner to run `claude`, type `/login` and click Resume, quoting Claude Code's message (one alert even if several runs fail at once);
* does not count the run against the task. The task keeps its status and its failure count. A resumed run gets its session and prompt back, and a fresh run starts fresh again.

**Consequences.** A login problem costs one run, not three per task, and the owner is told exactly what to do. Detection relies on undocumented print-mode text and the `error` field (verified against Claude Code 2.1.327). If either changes, runs fall back to the old behavior: three failures, then a blocked task. `asf doctor --login` remains the way to check the login before starting.
