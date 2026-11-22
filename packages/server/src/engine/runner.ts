import {
  compactMessages,
  ENGINE_NUDGE,
  ENGINE_PREAMBLE,
  ENGINE_TOOL_NAMES,
  ENGINE_TOOLS,
  engineCallId,
  estimateTokens,
  guardDecision,
  normalizeToolCall,
  parseModelRef,
  progressSummary,
  providerPreset,
  parseStreamLine,
  pickKey,
  realpathDeep,
  type ChatMessage,
  type GuardContext,
  type ToolCallMsg,
} from "@asf/core";
import fs from "node:fs";
import path from "node:path";
import { killTree, type AgentRunner, type RunHandlers, type RunSpec } from "../runner.ts";
import { catalogFor, type ModelCatalog } from "./catalog.ts";
import { chatCompletion } from "./client.ts";
import type { KeyStore } from "./keys.ts";
import { loadSession, saveSession } from "./sessions.ts";
import { runTool, type ToolOutcome } from "./tools.ts";

// The built-in engine: AI Software Factory runs the agent loop itself against OpenAI-compatible APIs (free tiers,
// local models), using the team's own keys. It writes the same stream-json lines `claude -p` does, so the
// orchestrator, the feed, the transcript, usage accounting, and the pauses work unchanged.

export interface EngineSettings {
  engine_models: { strong: string[]; fast: string[] };
  /** Also use each key's best model after the lists (default on). */
  engine_auto_models?: boolean;
  engine_context_tokens: number;
  /** Turns per run for the built-in engine (the role's own limit still applies when lower). */
  engine_max_turns?: number;
}

export interface EngineRunnerOptions {
  keys: KeyStore;
  /** Each key's best model, for the automatic picks (default: the key store's shared catalog). */
  catalog?: ModelCatalog;
  /** Read at the start of every run, so Settings changes apply to the next run. */
  settings: () => EngineSettings;
}

interface ActiveEngineRun {
  ac: AbortController;
  children: Set<number>;
  killed: boolean;
  timedOut: boolean;
  done: Promise<void>;
}

interface Call {
  id: string;
  name: string;
  input: Record<string, any>;
  parseError?: string;
}

const MAX_NETWORK_RETRIES = 3;
/** Room a request needs for the conversation itself, next to the instructions. */
const MIN_HISTORY_TOKENS = 3000;
/** Tokens the tool definitions add to every request. */
const TOOLS_TOKENS = Math.ceil(JSON.stringify(ENGINE_TOOLS).length / 4);
/** When every key is limited but the earliest reset is this close (a per-minute limit), the run waits for it. */
const MAX_INLINE_WAIT_MS = 90_000;

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal.aborted) return resolve();
    const t = setTimeout(resolve, ms);
    signal.addEventListener(
      "abort",
      () => {
        clearTimeout(t);
        resolve();
      },
      { once: true },
    );
  });
}

/**
 * The model's tool calls, cleaned up: our own ids (valid for every provider, so a run can switch provider), tool
 * and argument names mapped to the real ones, and arguments parsed (a parse error goes back to the model).
 */
function normalizeCalls(raw: ToolCallMsg[] | undefined, messageIndex: number): { calls: Call[]; history: ToolCallMsg[] } {
  const calls: Call[] = [];
  const history: ToolCallMsg[] = [];
  (raw ?? []).forEach((c, i) => {
    const id = engineCallId(messageIndex, i);
    const args = String(c.function?.arguments ?? "") || "{}";
    let input: Record<string, any> = {};
    let parseError: string | undefined;
    try {
      const v = JSON.parse(args);
      if (v && typeof v === "object" && !Array.isArray(v)) input = v;
      else parseError = "arguments must be a JSON object";
    } catch (e) {
      parseError = (e as Error).message;
    }
    const n = normalizeToolCall(String(c.function?.name ?? ""), input);
    calls.push({ id, name: n.name, input: n.input, parseError });
    history.push({ id, type: "function", function: { name: n.name, arguments: parseError ? args : JSON.stringify(n.input) } });
  });
  return { calls, history };
}

/**
 * The models a run tries, in order: a per-role model from Settings (when it names a provider; Claude aliases like
 * "sonnet" do not), then its own list (quick models for light work, main models otherwise), then (unless turned
 * off) the automatic choice for its level (small models for light work, the strongest for complex work, from
 * every working key), then the other list. A provider or model that runs out hands over to the next, and a new key
 * works at once. Without a level (older callers), the other list comes before the automatic picks.
 */
export function engineChain(spec: Pick<RunSpec, "model" | "tier" | "level">, s: EngineSettings, auto: string[] = []): string[] {
  const { strong, fast } = s.engine_models;
  const light = spec.level ? spec.level === "light" : spec.tier === "fast";
  const [mine, other] = light ? [fast, strong] : [strong, fast];
  const own = spec.model && parseModelRef(spec.model) ? [spec.model] : [];
  const autos = s.engine_auto_models === false ? [] : auto;
  return [...new Set(spec.level ? [...own, ...mine, ...autos, ...other] : [...own, ...mine, ...other, ...autos])];
}

/** A model that failed in a way that will not change (no tool calling, unknown id) is left out of automatic picks. */
const PERMANENT_MODEL_ERROR = /tool|not.?found|does not exist|unknown model|no such model|unsupported|not supported|not available|404|not free on this account/i;

export class EngineRunner implements AgentRunner {
  private runs = new Map<string, ActiveEngineRun>();
  private readonly opts: EngineRunnerOptions;
  /** Request size limits providers reported, per model, so later runs start within them. */
  private readonly learnedBudgets = new Map<string, number>();

  constructor(opts: EngineRunnerOptions) {
    this.opts = opts;
  }

  authHelp(): { reason: string; alert: string } {
    return {
      reason: "No working API key",
      alert:
        "None of the team's API keys works for the chosen models, so no agent can work. Open Keys to add or fix a key (or run `asf keys add`), check the models in Settings, then click Resume.",
    };
  }

  /** The owner clicked Resume (usually after fixing keys): try every key again. */
  reset(): void {
    for (const k of this.opts.keys.list()) if (k.invalid) this.opts.keys.setInvalid(k.id, null);
    this.opts.keys.clearCooldowns();
  }

  start(spec: RunSpec, handlers: RunHandlers): { pid: number | undefined } {
    const e: ActiveEngineRun = { ac: new AbortController(), children: new Set(), killed: false, timedOut: false, done: Promise.resolve() };
    const timer = setTimeout(() => {
      e.timedOut = true;
      e.ac.abort();
    }, spec.timeoutMs);
    this.runs.set(spec.runId, e);
    let exited = false;
    const h: RunHandlers = {
      onEvent: (ev) => handlers.onEvent(ev),
      onExit: (x) => {
        if (exited) return;
        exited = true;
        handlers.onExit(x);
      },
    };
    e.done = this.loop(spec, h, e)
      .catch((err: Error) => {
        console.error("[asf] engine run failed", err);
        // The orchestrator must always hear that the run ended, or its task would look busy forever.
        h.onExit({ code: 1, signal: null, timedOut: e.timedOut, killed: e.killed, stderr: `engine error: ${err.message}` });
      })
      .finally(() => {
        clearTimeout(timer);
        this.runs.delete(spec.runId);
      });
    return { pid: undefined };
  }

  private async loop(spec: RunSpec, h: RunHandlers, e: ActiveEngineRun): Promise<void> {
    fs.mkdirSync(path.dirname(spec.streamFile), { recursive: true });
    const out = fs.createWriteStream(spec.streamFile, { flags: "a" });
    const emit = (o: Record<string, unknown>) => {
      const line = JSON.stringify(o);
      out.write(`${line}\n`);
      for (const ev of parseStreamLine(line)) {
        try {
          h.onEvent(ev);
        } catch (err) {
          console.error("[asf] stream handler error", err);
        }
      }
    };
    const settings = this.opts.settings();
    const catalog = this.opts.catalog ?? catalogFor(this.opts.keys);
    // The model lists are cached; this only waits when a key is new or a list is hours old.
    if (settings.engine_auto_models !== false) await catalog.refresh().catch(() => {});
    const chain = engineChain(spec, settings, settings.engine_auto_models === false ? [] : catalog.autoRefs(spec.level));
    const sessionsDir = spec.sessionsDir ?? path.join(path.dirname(path.dirname(spec.streamFile)), "sessions");
    const sessionId = spec.sessionId;
    const history: ChatMessage[] = (spec.resume ? loadSession(sessionsDir, sessionId) : null) ?? [];
    // Resuming (after a pause, a limit, a restart, or an answer): remind the agent what it already did, so it
    // carries on instead of starting over even when a small model only sees the latest steps.
    const progress = history.length ? progressSummary(history) : null;
    history.push({ role: "user", content: progress ? `${spec.prompt}\n\n## Your progress so far in this task\n\n${progress}` : spec.prompt });
    const readSystem = (file: string | undefined) => {
      try {
        return file ? `${ENGINE_PREAMBLE}\n${fs.readFileSync(file, "utf8")}` : null;
      } catch {
        return null;
      }
    };
    // The full instructions include the role's skills (about 10k tokens). Models with a smaller per-request limit
    // (many free tiers) get the short version, which lists the skills by path for the agent to read.
    const fullSystem = readSystem(spec.systemFile) ?? ENGINE_PREAMBLE;
    const leanSystem = readSystem(spec.leanSystemFile) ?? fullSystem;
    const fullTokens = estimateTokens([{ role: "system", content: fullSystem }]) + TOOLS_TOKENS;
    const leanTokens = estimateTokens([{ role: "system", content: leanSystem }]) + TOOLS_TOKENS;
    const guard = this.readGuard(spec);
    const ctx = { cwd: spec.cwd, env: spec.env, signal: e.ac.signal, runId: spec.runId, children: e.children };
    // Tests only (a fake scenario is set): tell the scripted fake provider which run is asking.
    const testHeaders = spec.env.ASF_FAKE_SCENARIO
      ? { "x-asf-run": spec.runId, "x-asf-role": spec.env.ASF_ROLE ?? "", "x-asf-task": spec.env.ASF_TASK ?? "", "x-asf-mode": spec.env.ASF_MODE ?? "", "x-asf-resume": spec.resume ? "1" : "" }
      : undefined;

    emit({ type: "system", subtype: "init", session_id: sessionId, cwd: spec.cwd, model: chain[0] ?? "none", tools: ENGINE_TOOL_NAMES, permissionMode: "engine" });

    const usage = { input: 0, output: 0, cacheRead: 0 };
    let turns = 0;
    let isError = false;
    let subtype = "success";
    let resultText = "";
    // Each model's request budget (the whole request: instructions, tools, and history). Starts at the setting and
    // shrinks to what a provider says its limit is; remembered across runs.
    const budgetOf = (ref: string) => Math.min(settings.engine_context_tokens, this.learnedBudgets.get(ref) ?? Number.POSITIVE_INFINITY);
    /** Models that cannot take this run (too small, no tool calling, unknown model …), with the reason. */
    const skipped = new Map<string, string>();
    let retries = 0;
    let usedTool = false;
    let nudged = false;
    /** Calls that keep failing the same way, to tell the agent to change course. */
    const repeats = new Map<string, { count: number; output: string }>();
    // Free tiers count requests per day: the engine's own cap stops a confused run early.
    const maxTurns = Math.min(spec.maxTurns, settings.engine_max_turns ?? spec.maxTurns);

    while (!e.ac.signal.aborted) {
      if (turns >= maxTurns) {
        isError = true;
        subtype = "error_max_turns";
        resultText = `Reached the turn limit (${maxTurns}).`;
        break;
      }
      const live = chain.filter((ref) => !skipped.has(ref));
      if (chain.length && !live.length) {
        isError = true;
        subtype = "error_during_execution";
        resultText = `None of the chosen models could take this run. ${[...skipped].map(([ref, why]) => `${ref}: ${why}`).join(" · ")}`.slice(0, 1500);
        break;
      }
      const pick = pickKey(live, this.opts.keys.list(), this.opts.keys.state);
      if (!pick.ok) {
        // A per-minute limit resets soon: wait inside the run instead of pausing the whole team.
        if (pick.reason === "limited" && pick.resetsAt - Date.now() <= MAX_INLINE_WAIT_MS) {
          const ms = Math.max(1000, pick.resetsAt - Date.now() + 500);
          emit({ type: "system", subtype: "api_retry", error: `every key for these models is at its per-minute limit; waiting ${Math.ceil(ms / 1000)} s`, attempt: retries + 1 });
          await sleep(ms, e.ac.signal);
          continue;
        }
        isError = true;
        subtype = "error_during_execution";
        // These texts are what the stream parser recognizes as a usage limit (with a reset time) or a login failure.
        resultText = pick.reason === "limited" ? `${pick.message}: usage limit reached|${Math.ceil(pick.resetsAt / 1000)}` : `Invalid API key · ${pick.message}`;
        break;
      }
      const budget = budgetOf(pick.ref);
      const useFull = fullTokens + MIN_HISTORY_TOKENS <= budget;
      const sysTokens = useFull ? fullTokens : leanTokens;
      if (sysTokens + MIN_HISTORY_TOKENS > budget) {
        skipped.set(pick.ref, `its limit (about ${budget} tokens per request) is too small even for the short instructions`);
        continue;
      }
      const key = this.opts.keys.get(pick.key.id)!;
      this.opts.keys.touch(key.id);
      const r = await chatCompletion({
        baseUrl: this.opts.keys.baseUrl(key),
        apiKey: key.key,
        model: pick.model,
        messages: [{ role: "system", content: useFull ? fullSystem : leanSystem }, ...compactMessages(history, budget - sysTokens)],
        tools: ENGINE_TOOLS,
        signal: e.ac.signal,
        testHeaders,
      });
      if (!r.ok) {
        if (r.aborted || e.ac.signal.aborted) break;
        const err = r.error;
        emit({ type: "system", subtype: "api_retry", error: `${pick.ref} (${key.label}'s key): ${err.message}`.slice(0, 300), attempt: retries + 1 });
        if (err.kind === "auth") this.opts.keys.setInvalid(key.id, err.message);
        else if (err.kind === "limited") {
          // Providers that limit each model separately (Groq, Gemini) keep serving the key's other models.
          const perModel = providerPreset(key.provider)?.limitScope === "model";
          this.opts.keys.cooldown(key.id, err.resetsAt ?? Date.now() + 60_000, perModel ? pick.model : undefined);
        }
        else if (err.kind === "context") {
          // Shrink to the limit the provider reported (or halve), and try again; give up on this model only when
          // not even the short instructions fit.
          let next = err.limit ? Math.floor(err.limit * 0.85) : Math.floor(budget / 2);
          // Token counts are estimates: if the reported limit does not shrink the request, step down anyway, but
          // never far below what the provider reported (that would rule the model out for every later run too).
          if (next >= budget) next = Math.floor(budget * 0.8);
          const floor = err.limit ? Math.floor(err.limit * 0.6) : 0;
          if (next >= floor && next >= leanTokens + MIN_HISTORY_TOKENS) this.learnedBudgets.set(pick.ref, next);
          else skipped.set(pick.ref, err.message);
        } else if (err.kind === "retry") {
          retries++;
          if (retries > MAX_NETWORK_RETRIES) {
            // This provider is down for now: let the other keys and models take over.
            this.opts.keys.cooldown(key.id, Date.now() + 60_000);
            retries = 0;
          } else await sleep(2000 * 2 ** (retries - 1), e.ac.signal);
        } else {
          // This model cannot serve the run (no tool calling, unknown id, …): the next model in the list takes over.
          skipped.set(pick.ref, err.message);
          if (PERMANENT_MODEL_ERROR.test(err.message)) catalog.markBad(pick.ref);
        }
        continue;
      }
      retries = 0;
      turns++;
      usage.input += r.usage.input;
      usage.output += r.usage.output;
      usage.cacheRead += r.usage.cacheRead;
      this.opts.keys.recordUsage(key.id, r.usage.input + r.usage.cacheRead, r.usage.output);

      const { calls, history: callHistory } = normalizeCalls(r.message.tool_calls, history.length);
      const text = (r.message.content ?? "").trim();
      emit({
        type: "assistant",
        session_id: sessionId,
        message: {
          role: "assistant",
          model: pick.model,
          content: [...(text ? [{ type: "text", text }] : []), ...calls.map((c) => ({ type: "tool_use", id: c.id, name: c.name, input: c.input }))],
          usage: { input_tokens: r.usage.input, output_tokens: r.usage.output, cache_read_input_tokens: r.usage.cacheRead, cache_creation_input_tokens: 0 },
        },
      });
      // Content is always a string (some providers reject null), and never empty without tool calls.
      history.push(callHistory.length ? { role: "assistant", content: text, tool_calls: callHistory } : { role: "assistant", content: text || "Done." });
      if (!calls.length) {
        if (!usedTool && !nudged) {
          // A weaker model described the work instead of doing it: ask once, then accept its answer.
          nudged = true;
          history.push({ role: "user", content: ENGINE_NUDGE });
          continue;
        }
        resultText = text || "Done.";
        break;
      }
      usedTool = true;
      for (const c of calls) {
        let outcome: ToolOutcome;
        if (e.ac.signal.aborted) outcome = { ok: false, output: "The run was stopped." };
        else if (c.parseError) outcome = { ok: false, output: `Your ${c.name || "tool"} call had invalid JSON arguments (${c.parseError}). Send it again with valid JSON.` };
        else {
          // Without a readable guard file only reading is allowed: the same refusal the hook gives.
          const g = guard
            ? guardDecision({ tool_name: c.name, tool_input: c.input, cwd: spec.cwd }, guard)
            : ["Read", "Grep", "Glob", "TodoWrite"].includes(c.name)
              ? { allow: true }
              : { allow: false, reason: "AI Software Factory guard: run context missing; refusing tool call." };
          if (!g.allow) {
            outcome = { ok: false, output: g.reason ?? "AI Software Factory guard: blocked" };
            void this.reportBlock(spec, guard, c, outcome.output);
          } else outcome = await runTool(c.name, c.input, ctx);
        }
        outcome = this.noteRepeats(repeats, c, outcome);
        emit({ type: "user", session_id: sessionId, message: { role: "user", content: [{ type: "tool_result", tool_use_id: c.id, is_error: !outcome.ok, content: outcome.output }] } });
        history.push({ role: "tool", tool_call_id: c.id, content: outcome.output });
      }
      saveSession(sessionsDir, sessionId, history);
    }

    if (e.ac.signal.aborted) {
      isError = true;
      subtype = "error_during_execution";
      resultText = e.timedOut ? "The run reached its time limit." : "The run was stopped.";
    }
    try {
      saveSession(sessionsDir, sessionId, history);
    } catch {
      /* the run result matters more */
    }
    // Servers an agent started in the background end with its run, as with Claude Code.
    await Promise.all([...e.children].map((pid) => killTree(pid)));
    emit({
      type: "result",
      subtype,
      is_error: isError,
      num_turns: turns,
      total_cost_usd: 0,
      usage: { input_tokens: usage.input, output_tokens: usage.output, cache_read_input_tokens: usage.cacheRead, cache_creation_input_tokens: 0 },
      session_id: sessionId,
      result: resultText,
    });
    await new Promise<void>((resolve) => out.end(resolve));
    h.onExit({ code: isError ? 1 : 0, signal: null, timedOut: e.timedOut, killed: e.killed, stderr: "" });
  }

  /**
   * The same call failing with the same message again and again: smaller models tend to repeat a failing command
   * instead of fixing its cause (a plan submitted seven times with the same missing fields). From the third time,
   * the result says so, which is usually enough to make the model read the message and change something.
   */
  private noteRepeats(repeats: Map<string, { count: number; output: string }>, c: Call, outcome: ToolOutcome): ToolOutcome {
    const sig = `${c.name}:${JSON.stringify(c.input)}`;
    if (outcome.ok) {
      repeats.delete(sig);
      return outcome;
    }
    const prev = repeats.get(sig);
    const count = prev && prev.output === outcome.output ? prev.count + 1 : 1;
    repeats.set(sig, { count, output: outcome.output });
    if (count < 3) return outcome;
    return {
      ok: false,
      output: `${outcome.output}\n\n(AI Software Factory: this exact call has now failed ${count} times with the same result. Running it again will not help. Read the message above, change what it points to (if it describes a format or names a template, open that and follow it), and only then try again.)`,
    };
  }

  private readGuard(spec: RunSpec): (GuardContext & { projectId?: string }) | null {
    const file = spec.env.ASF_GUARD_FILE;
    if (!file) return null;
    try {
      return { ...(JSON.parse(fs.readFileSync(file, "utf8")) as GuardContext & { projectId?: string }), realpath: realpathDeep };
    } catch {
      return null;
    }
  }

  private async reportBlock(spec: RunSpec, guard: (GuardContext & { projectId?: string }) | null, c: Call, reason: string): Promise<void> {
    const url = spec.env.ASF_SERVER_URL;
    const token = spec.env.ASF_TOKEN;
    if (!url || !token || !guard?.projectId) return;
    try {
      await fetch(`${url}/api/projects/${guard.projectId}/guard-block`, {
        method: "POST",
        headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
        body: JSON.stringify({ tool: c.name, reason, target: String(c.input.file_path ?? c.input.command ?? "").slice(0, 300) }),
        signal: AbortSignal.timeout(1500),
      });
    } catch {
      /* the block itself is what matters */
    }
  }

  async kill(runId: string): Promise<void> {
    const e = this.runs.get(runId);
    if (!e) return;
    e.killed = true;
    e.ac.abort();
    await Promise.all([...e.children].map((pid) => killTree(pid)));
    await Promise.race([e.done, new Promise((r) => setTimeout(r, 1500))]);
  }

  async killAll(): Promise<void> {
    await Promise.all([...this.runs.keys()].map((id) => this.kill(id)));
  }

  active(): string[] {
    return [...this.runs.keys()];
  }
}
