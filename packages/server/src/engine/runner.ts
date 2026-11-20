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
import { chatCompletion } from "./client.ts";
import type { KeyStore } from "./keys.ts";
import { loadSession, saveSession } from "./sessions.ts";
import { runTool, type ToolOutcome } from "./tools.ts";

// The built-in engine: AI Software Factory runs the agent loop itself against OpenAI-compatible APIs (free tiers,
// local models), using the team's own keys. It writes the same stream-json lines `claude -p` does, so the
// orchestrator, the feed, the transcript, usage accounting, and the pauses work unchanged.

export interface EngineSettings {
  engine_models: { strong: string[]; fast: string[] };
  engine_context_tokens: number;
  /** Turns per run for the built-in engine (the role's own limit still applies when lower). */
  engine_max_turns?: number;
}

export interface EngineRunnerOptions {
  keys: KeyStore;
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
/** Never trim the conversation below this, however big the system prompt is. */
const MIN_HISTORY_TOKENS = 4000;

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

export function engineChain(spec: Pick<RunSpec, "model" | "tier">, s: EngineSettings): string[] {
  const { strong, fast } = s.engine_models;
  const tier = spec.tier === "fast" && fast.length ? fast : strong.length ? strong : fast;
  // A per-role model in Settings wins when it names a provider ("groq:…"); Claude aliases like "sonnet" do not.
  const own = spec.model && parseModelRef(spec.model) ? [spec.model] : [];
  return [...new Set([...own, ...tier])];
}

export class EngineRunner implements AgentRunner {
  private runs = new Map<string, ActiveEngineRun>();
  private readonly opts: EngineRunnerOptions;

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
    for (const id of Object.keys(this.opts.keys.state)) this.opts.keys.state[id] = { ...this.opts.keys.state[id], cooldownUntil: 0 };
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
    const chain = engineChain(spec, settings);
    const sessionsDir = spec.sessionsDir ?? path.join(path.dirname(path.dirname(spec.streamFile)), "sessions");
    const sessionId = spec.sessionId;
    const history: ChatMessage[] = (spec.resume ? loadSession(sessionsDir, sessionId) : null) ?? [];
    history.push({ role: "user", content: spec.prompt });
    let system = ENGINE_PREAMBLE;
    try {
      system += `\n${fs.readFileSync(spec.systemFile, "utf8")}`;
    } catch {
      /* the orchestrator always writes it; keep going with the preamble */
    }
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
    // The context budget covers the whole request, so the (large) system prompt counts against it.
    const systemTokens = estimateTokens([{ role: "system", content: system }]);
    let budget = settings.engine_context_tokens;
    let retries = 0;
    let usedTool = false;
    let nudged = false;
    // Free tiers count requests per day: the engine's own cap stops a confused run early.
    const maxTurns = Math.min(spec.maxTurns, settings.engine_max_turns ?? spec.maxTurns);

    while (!e.ac.signal.aborted) {
      if (turns >= maxTurns) {
        isError = true;
        subtype = "error_max_turns";
        resultText = `Reached the turn limit (${maxTurns}).`;
        break;
      }
      const pick = pickKey(chain, this.opts.keys.list(), this.opts.keys.state);
      if (!pick.ok) {
        isError = true;
        subtype = "error_during_execution";
        // These texts are what the stream parser recognizes as a usage limit (with a reset time) or a login failure.
        resultText = pick.reason === "limited" ? `${pick.message}: usage limit reached|${Math.ceil(pick.resetsAt / 1000)}` : `Invalid API key · ${pick.message}`;
        break;
      }
      const key = this.opts.keys.get(pick.key.id)!;
      this.opts.keys.touch(key.id);
      const r = await chatCompletion({
        baseUrl: this.opts.keys.baseUrl(key),
        apiKey: key.key,
        model: pick.model,
        messages: [{ role: "system", content: system }, ...compactMessages(history, Math.max(MIN_HISTORY_TOKENS, budget - systemTokens))],
        tools: ENGINE_TOOLS,
        signal: e.ac.signal,
        testHeaders,
      });
      if (!r.ok) {
        if (r.aborted || e.ac.signal.aborted) break;
        const err = r.error;
        emit({ type: "system", subtype: "api_retry", error: `${pick.ref} (${key.label}'s key): ${err.message}`.slice(0, 300), attempt: retries + 1 });
        if (err.kind === "auth") this.opts.keys.setInvalid(key.id, err.message);
        else if (err.kind === "limited") this.opts.keys.cooldown(key.id, err.resetsAt ?? Date.now() + 60_000);
        else if (err.kind === "context" && budget > 6000) budget = Math.floor(budget / 2);
        else if (err.kind === "retry") {
          retries++;
          if (retries > MAX_NETWORK_RETRIES) {
            // This provider is down for now: let the other keys and models take over.
            this.opts.keys.cooldown(key.id, Date.now() + 60_000);
            retries = 0;
          } else await sleep(2000 * 2 ** (retries - 1), e.ac.signal);
        } else {
          isError = true;
          subtype = "error_during_execution";
          resultText = `${pick.ref}: ${err.message}`;
          break;
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
