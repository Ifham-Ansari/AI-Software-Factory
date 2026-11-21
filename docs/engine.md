# The built-in engine: AI Software Factory without a subscription

AI Software Factory can run its agents in two ways:

| Engine | What it needs | Best for |
|---|---|---|
| **Claude Code** (default) | A Claude subscription, or an Anthropic API key, through the `claude` CLI | The best results on large builds |
| **Built-in engine** | Free API keys (Gemini, Groq, OpenRouter, Mistral, Cerebras), or a model running on your own computer (Ollama, LM Studio) | Using AI Software Factory without paying for anything |

You choose per project in **Settings → Agent engine**. Switching takes effect on the next agent run, with nothing to restart.

## Get started in five minutes

1. **Get a free key.** Open **API keys** in the dashboard (or run `asf keys providers`). Each provider has a "Get a free key" link:
   * Google Gemini: <https://aistudio.google.com/apikey>
   * Groq: <https://console.groq.com/keys>
   * OpenRouter: <https://openrouter.ai/keys> (models ending in `:free` cost nothing)
   * Mistral: <https://console.mistral.ai/api-keys>
   * Cerebras: <https://cloud.cerebras.ai>
   * No key at all: install [Ollama](https://ollama.com) or [LM Studio](https://lmstudio.ai) and run a model on your computer.
2. **Add it.** On **API keys**, pick the provider, type your name under "Whose key", paste the key, and click **Add key**. It is checked at once (checking uses no tokens). From a terminal, `asf keys add groq --label "Your name"` does the same and asks for the key.
3. **Switch the engine.** In **Settings → Agent engine**, choose **Built-in engine**.
4. **Pick models.** Under **Main models**, add one or more models from the list (it is read live from your providers). Under **Quick models**, optionally add a smaller, faster one for routine work. Click **Save settings**.
5. **Send a request** on the Idea screen. Start with something small; the quick track suits free tiers best.

## Choosing models

Pick models that **support tool calling** (also called function calling): agents work only through tools. The provider's model list or documentation says which do. Bigger models do much better at long, multi-step work:

* On cloud free tiers, choose the largest model with tool calling that the provider offers for free (for example a 70B-class Llama on Groq, a Flash model on Gemini, or a `:free` model marked "tools" on OpenRouter).
* On your own computer, a coding model of about 30B parameters needs roughly 16 to 24 GB of GPU memory; smaller ones work for small changes.

The lists are **ordered**. When the first model runs out of free quota, or cannot take a run at all (no tool calling, or a limit smaller than one request), the next one takes over in the middle of the same conversation. A run uses its own list first and the other list as a backup, so quick runs fall back to your main models and the other way round. Put your best model first and add a second provider as backup.

**Small per-request limits.** Some free tiers allow only a few thousand tokens per request or per minute (Groq's free tier allows 8,000 tokens per minute for some models). An agent's full instructions (its role's skills) are about 10,000 tokens. When a provider reports a smaller limit, AI Software Factory remembers it and sends that model **short instructions** instead: the same rules, with the skills listed by file path for the agent to read when it needs them. This works, but small-limit models do noticeably worse and run slowly (one request a minute at 8,000 tokens per minute). Prefer them as a backup, not as your first model.

Model names are written `provider:model`, for example `groq:llama-3.3-70b-versatile`. For a custom or local server added with its own base URL, the provider part is the key's id (shown in the model picker).

## A team of several people

One person runs AI Software Factory on their computer, and each teammate adds **their own** key there once, under their own name. AI Software Factory then:

* spreads requests over every working key;
* moves a running agent to the next key when one hits its limit, without losing its work;
* waits inside the run when every key is at a per-minute limit that resets within about a minute and a half;
* pauses the team when every key is limited for longer (a daily limit), and carries on by itself after the earliest reset;
* shows on **API keys** each key's status (ready, limited until a time, or rejected) and how much each teammate's keys were used today.

Keys are stored only on that computer, in `~/.asf/keys.json`, shared by all its projects, and never shown in full again. Agents cannot read them.

**Use your own key, and follow your provider's terms.** Each key belongs to the person who added it. Some providers do not allow a key to be shared with others, and creating several accounts to get around a free limit breaks almost every provider's terms (and gets accounts closed). Combine different people's own keys and different providers instead.

## Making free limits last

Free tiers limit **requests per day** and **tokens per minute**. Every agent turn is one request, and every request resends the agent's instructions plus recent work. AI Software Factory keeps this small:

* tool output is capped and long files are read in pages;
* older steps are trimmed so that each request stays under **Size of each request** (Settings; lower it when a provider's per-minute limit is small);
* **Turns per run** (Settings, default 50) stops a confused agent before it uses your whole day;
* the **Team builder** shows an estimate of API requests before you start a build.

Practical tips:

* Prefer the **quick** and **standard** tracks; a full product is dozens of runs.
* Keep **Agents running at once** at 1 or 2 on free tiers, so per-minute limits are not hit all at once.
* Add keys from more than one provider, so one provider's daily limit does not stop the team.

## What happens when something goes wrong

| You see | What it means | What to do |
|---|---|---|
| Paused: "No working API key" | Every key for the chosen models was rejected, or there is none | Fix or add a key on **API keys**, check the models in Settings, then click **Resume** (Resume tries every key again) |
| Paused: usage limit, resumes at a time | Every key has hit its limit | Wait (it resumes by itself), or add another key or provider and click **Resume** |
| A key shows "rejected" | The provider refused it (wrong, expired, or revoked) | Create a new key, add it, and remove the old one |
| A run ends with "does not support tools" | The model cannot call tools, and no other model in your lists could take over | Choose a model with tool calling |
| A run ends with "None of the chosen models could take this run" | Every model in both lists failed; the message names each one and why (for example "Request too large … Limit 8000") | Add a model with a bigger limit (another provider), or check the model names |
| Agents are slow, with "waiting N s" in the feed | Every key is at a per-minute limit | Add a key from another provider, or lower **Agents running at once** |
| Agents finish without doing the work | The model is too small for the task | Use a bigger model, or a smaller request |

## Privacy

With the built-in engine, everything an agent reads (your idea, documents, code, command output) is sent to the provider you chose. Free tiers have weaker data terms than paid plans; Google, for example, says it may use Gemini free-tier prompts to improve its models. Do not use a free tier for code or data you may not share. A local model (Ollama, LM Studio) keeps everything on your computer.

## For developers

How the engine works and why it was built this way: [decision 0014](decisions/0014-builtin-engine.md). The code is in `packages/server/src/engine/` (runner, tools, client, key store, sessions) and `packages/core/src/engine/` (tool schemas, provider errors, key selection, trimming). Tests run it against `fake-llm` (`packages/fake-claude/src/llm.ts`), a scripted OpenAI-compatible server: no real provider is called.
