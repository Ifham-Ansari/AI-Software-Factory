# The built-in engine: AI Software Factory without a subscription

AI Software Factory can run its agents in two ways:

| Engine | What it needs | Best for |
|---|---|---|
| **Claude Code** (default) | A Claude subscription, or an Anthropic API key, through the `claude` CLI | The best results on large builds |
| **Built-in engine** | Free API keys from any of the providers below, or a model running on your own computer (Ollama, LM Studio) | Using AI Software Factory without paying for anything |

You choose per project in **Settings → Agent engine**. Switching takes effect on the next agent run, with nothing to restart.

## Free providers

Each provider's free allowance is separate, and the built-in engine uses all the keys you add, so **every provider you add increases what the team can do per day**. Researched in November 2026; free tiers change often, so each note in the app says what to check.

| Provider | Free allowance (as published) | Good to know |
|---|---|---|
| [Google Gemini](https://aistudio.google.com/apikey) | Flash, Flash-Lite, and Gemma models, daily limits per model | Pro models are paid. Outside the EEA, UK, and Switzerland, free-tier prompts may be used to improve Google's products |
| [Groq](https://console.groq.com/keys) | Per model, for example 1,000 requests and 200k tokens a day on its largest | Very fast. Small per-minute token limits on the big models |
| [OpenRouter](https://openrouter.ai/keys) | `:free` models: 20 a minute, 50 a day per account (1,000 a day after a one-time $10 top-up) | Free providers may log prompts |
| [NVIDIA API Catalog](https://build.nvidia.com) | About 40 requests a minute, large models (Nemotron Ultra 550B) | For prototyping and development, not production; use is logged |
| [Mistral](https://console.mistral.ai/api-keys) | Experiment plan, about 1 request a second per model | Phone verification; requests may be used for training |
| [Z.ai](https://z.ai/manage-apikey/apikey-list) | GLM-4.x Flash models free, with tool calling | One request at a time per model; GLM-5.x and FlashX models are paid |
| [Cloudflare Workers AI](https://dash.cloudflare.com/profile/api-tokens) | 10,000 Neurons a day per account | Needs your account id in the base URL; some newer models are paid |
| [SambaNova](https://cloud.sambanova.ai/apis) | Small per-model limits, no card | Check the current limits in your account |
| [Ollama Cloud](https://ollama.com/settings/keys) | Light use: one model at a time, session and weekly limits | Limits are not published |
| [Kilo Gateway](https://app.kilo.ai) | `:free` models, about 200 requests an hour | Its free router may use providers that log prompts |
| OVHcloud AI Endpoints | Anonymous, **no key or signup**: 2 requests a minute per model | Hosted in the EU; slow but free |
| [LLM7.io](https://token.llm7.io) | Works without a key; a free token gives 100k tokens a day | The free quota may change without notice |
| [AxForge](https://axforge.ai) | 3M tokens every 30 days per account | Says prompts are not stored or used for training |
| [Cohere](https://dashboard.cohere.com/api-keys) | Trial key, about 1,000 calls a month | Non-commercial use only |
| [Cerebras](https://cloud.cerebras.ai) | Trial credit only (since mid-2026) | Needs a payment method |
| [Ollama](https://ollama.com), [LM Studio](https://lmstudio.ai) (your computer) | Unlimited | Needs a strong GPU; nothing leaves your computer |

Not included: **GitHub Models** (retired on 30 July 2026), **Hugging Face** (free accounts get only about $0.10 of credit a month), **Aion Labs** (20k tokens a day, less than one agent run), **ModelScope** and **SiliconFlow** (mainland China only), and services run by anonymous or volunteer hosts (your code would go to them). Any other OpenAI-compatible service can be added as **Other**.

## Get started in five minutes

1. **Get a free key** from one or more providers above (the **API keys** screen links to each one; `asf keys providers` lists them). OVHcloud works with no key at all.
2. **Add it.** On **API keys**, pick the provider, type your name under "Whose key", paste the key, and click **Add key**. It is checked at once (checking uses no tokens). From a terminal, `asf keys add groq --label "Your name"` does the same and asks for the key.
3. **Switch the engine.** In **Settings → Agent engine**, choose **Built-in engine** and click **Save settings**. It stays on the built-in engine until you choose otherwise there.
4. **Models are picked for you, per task** (see the next section). You can also choose your own under **Main models** and **Quick models**; yours are tried first.
5. **Send a request** on the Idea screen.

## Automatic model choice

AI Software Factory reads every key's model list and keeps the models that can drive an agent: chat models with tool calling, free ones only (on OpenRouter and Kilo only `:free` models, on Gemini no Pro models, on Z.ai only the GLM-4.x Flash models, on Cloudflare no paid models). It sorts them into **small**, **medium**, and **large** by their size and tier, and ranks them (newer, bigger, coding-oriented models first).

Then each agent run gets the size of model its task needs, decided by plain code (no model is asked):

| Level | Runs | Models tried first |
|---|---|---|
| **Light** | Sizing a request, answering a teammate, small (S) tasks and their reviews | Small, fast models |
| **Standard** | Medium (M) tasks, reviews and QA of larger tasks, discovery questions, fixes after review | Medium models |
| **Complex** | The PRD, design, architecture, plan, the app scaffold, large (L) tasks, merge and repair work, the release | The largest models |

A task that ended without finishing moves up one level for its next run (two after a second failure), and code for customer-facing or regulated projects never goes to the smallest models. After the preferred size come the other sizes as backups, from every provider. Standard and complex work never fall back to small models while a bigger one exists: when all the bigger models are at their limits, the run waits for them, because a small model would only loop on work it cannot do. (With only small models, they do everything.)

This saves your free allowance where it is scarce: the largest models usually have the smallest free limits, so routine work on small models leaves them for the work that needs them. **Settings → Automatic model choice** shows which models each level would use right now, and has a switch to turn the automatic choice off. A model that turns out not to work (no tool calling, an unknown id, or not free on your account) is dropped. The lists are read again every few hours, and whenever a key is added or tested; providers that do not list their models use the models AI Software Factory knows for them.

**Limits per model.** Groq, Gemini, Mistral, SambaNova, Z.ai, and OVHcloud limit each model separately: when one model reaches its limit, the same key keeps working with its other models. OpenRouter, NVIDIA, Cloudflare, Kilo, and the others limit the whole account, so the key rests until its reset. **API keys** shows "ready · 2 models resting" or "limited until …".

## Choosing models

Pick models that **support tool calling** (also called function calling): agents work only through tools. The provider's model list or documentation says which do. Bigger models do much better at long, multi-step work:

* On cloud free tiers, choose the largest model with tool calling that the provider offers for free (for example a 70B-class Llama on Groq, a Flash model on Gemini, or a `:free` model marked "tools" on OpenRouter).
* On your own computer, a coding model of about 30B parameters needs roughly 16 to 24 GB of GPU memory; smaller ones work for small changes.

Your own lists are **ordered** and come first. Light runs use **Quick models**, then the automatic choice, then **Main models**; other runs use **Main models**, then the automatic choice, then **Quick models**. When a model runs out of free quota, or cannot take a run at all (no tool calling, or a limit smaller than one request), the next one takes over in the middle of the same conversation. Leave the lists empty to let AI Software Factory choose everything. A model in your lists that its provider does not offer for free is marked **not a free model here** (for example an OpenRouter model without `:free`, or a Z.ai GLM-5 model): it would fail on every run, so pick the free variant or remove it.

**Small per-request limits.** Some free tiers allow only a few thousand tokens per request or per minute (Groq's free tier allows 8,000 tokens per minute for some models). An agent's full instructions (its role's skills) are about 10,000 tokens. When a provider reports a smaller limit, AI Software Factory remembers it and sends that model **short instructions** instead: the same rules, with the skills listed by file path for the agent to read when it needs them. This works, but small-limit models do noticeably worse and run slowly (one request a minute at 8,000 tokens per minute). Prefer them as a backup, not as your first model.

Model names are written `provider:model`, for example `groq:llama-3.3-70b-versatile`. For a custom or local server added with its own base URL, the provider part is the key's id (shown in the model picker).

## A team of several people

One person runs AI Software Factory on their computer, and each teammate adds **their own** key there once, under their own name. AI Software Factory then:

* spreads requests over every working key;
* moves a running agent to the next key when one hits its limit, without losing its work;
* waits inside the run when every key is at a per-minute limit that resets within about a minute and a half;
* waits when every key is limited for longer (a daily limit), shows **waiting for usage limits until …** in the header with a **Try now** button, and carries on by itself after the earliest reset; adding a key, a successful key test, or restarting AI Software Factory tries again at once;
* shows on **API keys** each key's status (ready, limited until a time, or rejected) and how much each teammate's keys were used today.

Keys are stored only on that computer, in `~/.asf/keys.json`, shared by all its projects, and never shown in full again. Agents cannot read them.

**Use your own key, and follow your provider's terms.** Each key belongs to the person who added it. Some providers do not allow a key to be shared with others, and creating several accounts to get around a free limit breaks almost every provider's terms (and gets accounts closed). Combine different people's own keys and different providers instead.

## Making free limits last

Free tiers limit **requests per day** and **tokens per minute**. Every agent turn is one request, and every request resends the agent's instructions plus recent work. AI Software Factory keeps this small:

* tool output is capped and long files are read in pages;
* once a file is written, its content is not sent again: the step keeps a pointer ("36,340 characters written to `home.html`; Read it to see them"), since the file is on disk;
* older steps are trimmed so that each request stays under **Size of each request** (Settings; lower it when a provider's per-minute limit is small), and the agent is told what the removed steps did, so it does not redo them;
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
| Header: **waiting for usage limits until …** | Every key the agents can use has hit its limit (often a daily one) | Wait (the agents carry on by themselves), or add a key from another provider (it is tried at once), or click **Try now** |
| A key shows "rejected" | The provider refused it (wrong, expired, or revoked) | Create a new key, add it, and remove the old one |
| A run ends with "does not support tools" | The model cannot call tools, and no other model in your lists could take over | Choose a model with tool calling |
| A run ends with "None of the chosen models could take this run" | Every model in both lists failed; the message names each one and why (for example "Request too large … Limit 8000") | Add a model with a bigger limit (another provider), or check the model names |
| Agents are slow, with "waiting N s" in the feed | Every key is at a per-minute limit | Add a key from another provider, or lower **Agents running at once** |
| A run names a model "not free on this account" | That model needs credits or a paid plan on its provider (HTTP 402, "requires more credits", "Insufficient balance") | Nothing breaks: the model is dropped and the next one takes over. Remove it from your lists (Settings marks it) |
| Agents finish without doing the work | The model is too small for the task | Use a bigger model, or a smaller request |
| An agent repeats the same failing step (for example `asf plan check` over and over) | The model does not follow what the error says. After the third identical failure it is told to change course, and `asf plan check` shows the task-file format | Add a key with a large free model (NVIDIA, OpenRouter `:free`, Groq) for planning. If the task gets blocked, click **Unblock** to retry |

## Picking up where it left off

Work is never thrown away when it stops: after a usage limit, the kill switch, a question to you, or a restart of AI Software Factory, the agent's run continues the same conversation (kept in `.asf/sessions/`) instead of starting a new one. Its first message then includes a short summary of its progress: the files it already wrote or edited, the `asf` commands that changed the board, and its checklist, with the instruction not to redo finished work. This matters most with small free models, which only see the latest steps of a long conversation. Files on disk are never undone by a stop; at worst an agent rereads one to check it is complete.

## Privacy

With the built-in engine, everything an agent reads (your idea, documents, code, command output) is sent to the provider you chose. Free tiers have weaker data terms than paid plans; Google, for example, says it may use Gemini free-tier prompts to improve its models. Do not use a free tier for code or data you may not share. A local model (Ollama, LM Studio) keeps everything on your computer.

## For developers

How the engine works and why it was built this way: [decision 0014](decisions/0014-builtin-engine.md). The code is in `packages/server/src/engine/` (runner, tools, client, key store, sessions) and `packages/core/src/engine/` (tool schemas, provider errors, key selection, trimming). Tests run it against `fake-llm` (`packages/fake-claude/src/llm.ts`), a scripted OpenAI-compatible server: no real provider is called.
