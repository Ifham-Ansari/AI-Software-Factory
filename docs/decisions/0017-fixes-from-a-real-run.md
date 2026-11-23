# 0017: Fixes from a real run on free models

**Status:** accepted · 2026-11-23

**Context.** We built a small static website (a bakery: home page, menu with search, contact form) the way a user would: a new folder, `asf up`, the built-in engine on the owner's free keys (OpenRouter, Groq, Mistral, Z.ai), and every decision made in the dashboard. The site got built and works, but the run took hours and hit many problems. Each one below is a deterministic fix: plain code, no extra model calls.

**Decision.**

* **Starting a project.** `asf up` in a new, empty folder sets that folder up as a project, even inside another project's folder (a folder of projects had itself been set up as one). Running it from a subfolder that has files still opens the enclosing project.
* **Models.**
  * When a provider lists only models that are not free (Z.ai lists its paid GLM-5 models), the catalog uses the preset's known free models; Z.ai's dated Flash ids count as free.
  * Settings says "Reading your providers' model lists…" while they load, instead of "No models yet: add a working key".
  * Models under 7B parameters are never routed to agent work.
  * Sizing a request (triage) and reviews or QA checks are at least standard work: on the smallest models they looped.
  * Groq's 429 "Request too large" means the request can never fit that model's per-minute limit. It is now treated like any request that is too large, not as a rate limit to wait for (it had been retried 429 times).
* **Plan check.** `asf plan check` (and submit) also refuses:
  * app files in `.asf/` (`asf_path`): the first plan put the website in `.asf/static/`;
  * an id that a started, finished, or cancelled task already has (`id_taken`), with the next free id suggested;
  * a verify command that checks files another task creates later (`verify_order`): it can only fail.

  Finished tasks' old files are not held to the `.asf/` rule.
* **Cancel and approvals.**
  * Cancelling moves the unfinished tasks' files to `.asf/tasks/cancelled/`, so the next plan starts clean.
  * Approving a document stops planning tasks still working on it, except the one that submitted the approved version, whose output still has to be merged. A second plan revision had kept editing the approved task files during the build.
  * A task closed this way is not handled as a failed run.
* **Guard.** Shell commands that create or change files (`mkdir`, `touch`, `cp`, `mv`, `tee`, `chmod`, and output redirects) are refused outside the worktree, except temp folders. This follows `cd` in the same line, Git Bash drive paths, and Windows paths in double quotes (now parsed as bash does). A lost agent had created folders in AI Software Factory's own source.
* **Agents that loop.**
  * The third identical successful call gets a note to move on (a finished page's check ran a dozen times instead of `asf task done`).
  * The latest read of each project document (`.asf/docs/`) stays whole in trimmed history (a planner re-read its PRD seven times).
  * An agent cannot ask itself (a tech lead asked `@tech-lead`, then answered itself).
* **Reviews and the release.**
  * Without git (direct mode), the review prompt carries the task's diff: the reviewer had spent 40 turns trying to get it.
  * The release follow-up from the owner's feedback may change the project's files (it could change none) and says plainly what to do.
  * The release summary in direct mode says the work is in the project folder, not on a branch, leaves out cancelled tasks, and uses the latest release QA report.
  * The Team builder's estimate counts only tasks still to do.

**Consequences.** The same run would now avoid the hidden folder, the duplicate planning, the stuck follow-up, and most loops. What remains is the free tiers themselves. The strongest free models ran out early (OpenRouter's 50 requests a day per account; Groq's 6,000 to 8,000 tokens a minute; Mistral's one request a second; Z.ai overloaded), so most work fell to medium models, which are slow and make more mistakes, and release QA did not finish within 50 turns. A Gemini or NVIDIA key, both with stronger free models, makes the biggest difference.
