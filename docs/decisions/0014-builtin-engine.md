# 0014: A built-in engine that runs agents on the team's own API keys

**Status:** accepted · 2026-11-21

**Context.** Every agent was a `claude -p` process, so AI Software Factory only worked with a Claude subscription or a paid Anthropic key. The project's goal is to be usable by people who cannot pay for one. Free API tiers (Gemini, Groq, OpenRouter's `:free` models, Mistral, Cerebras) and local models (Ollama, LM Studio) cost nothing, and almost all of them speak the OpenAI-compatible `/chat/completions` format with tool calling. Free tiers are small, though: a few thousand requests a day at best, low tokens per minute, and some keep prompts for training. A team of a few people often has several such keys between them.

Three ways were considered:
* Point Claude Code at a translating proxy (`ANTHROPIC_BASE_URL`). No code change, but it is not supported by Anthropic, and the product would still depend on Claude Code.
* Wrap an open-source agent CLI. Less code, but users install one more tool, and switching provider in the middle of a conversation (the key to stretching free limits) is out of our hands.
* Run the agent loop ourselves. More code, but nothing extra to install, the guard runs in-process, and AI Software Factory owns the conversation.

**Decision.** A third runner, `EngineRunner`, implements `AgentRunner` next to `ClaudeRunner`. A project's `engine` setting (`claude-code`, the default, or `builtin`) picks one per run through `RunnerRouter`, so switching needs no restart.

* **Same contract as `claude -p`.** The engine writes Claude-compatible stream-json (init, assistant `text`/`tool_use` with usage, user `tool_result`, result). Its tools use Claude Code's names and parameters (Read, Write, Edit, Bash, Grep, Glob, TodoWrite). So the stream parser, feed summaries, live transcript, usage accounting, and the usage-limit and login-failure pauses work unchanged.
* **Guard in-process.** Before every tool call the engine calls `guardDecision` with the run's `guard.json`, exactly what the hook does. A denial goes back to the model as a tool error and is reported to `/guard-block`.
* **Sessions.** The conversation is saved in `.asf/sessions/<session>.json`, so `--resume` semantics hold (questions, review rounds, pauses, restarts).
* **Team keys.** Keys are stored per computer in `~/.asf/keys.json`, each labelled with its owner, and shared by every project there. Before each request, `pickKey` (pure, in core) takes the least recently used healthy key for the first model in the chain that has one. A 429 cools that key down until its reset (parsed from each provider's headers or body), a 401/403 marks it rejected, and the same conversation continues on the next key or model. When every key is cooling down, the run ends as a usage limit with the earliest reset, so the existing pause-and-auto-resume applies. With no usable key, it ends as a login failure, and the pause says "No working API key". Resume clears rejected marks and cooldowns.
* **Models.** Settings has two ordered chains of `provider:model`: main (planning and building) and quick (the modes that already use a lighter model). Model lists come live from each provider's `GET /models`; nothing is hard-coded.
* **Free-tier thrift.** Tool output is capped (800 lines or 30k characters per read, 12k characters per command), each request is trimmed to `engine_context_tokens` (system prompt included: old tool output is stubbed first, then the oldest steps are dropped whole), and `engine_max_turns` caps requests per run. The Team builder shows an estimate of API requests.
* **Weaker models.** Common tool and argument names ("read_file", "path", "cmd") are mapped to the real ones. Invalid JSON arguments go back to the model as an error. A first reply without any tool call gets one nudge. Tool call ids are rewritten to 9 letters and digits, so any provider accepts the history.

The skills did not change: they never name Claude-specific tools.

**Consequences.** People without a subscription can use AI Software Factory, and a team can pool its free allowances legitimately (each person's own key). Small free models are clearly weaker than Claude at long agentic work. Quick and standard requests work; a full product needs more retries, and is best with the strongest free models or a local model on a good GPU. The engine depends on providers' OpenAI compatibility, which varies; the error classifier and request shape (no `additionalProperties` in tool schemas, string content) follow the strictest provider seen. Tests run the engine against `fake-llm`, a scripted OpenAI-compatible server that acts out the same scenario files as fake-claude, and the full-track happy path runs on both engines.
