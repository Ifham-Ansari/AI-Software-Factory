// fake-llm: a scripted OpenAI-compatible /chat/completions server, the built-in engine's test double. It acts out
// the same scenario files as fake-claude (ASF_FAKE_SCENARIO), but as tool calls the engine really executes
// (Write, Bash, TodoWrite), so tests exercise the engine's tools, guard, and loop. The engine tells it which run
// is asking through x-asf-* headers, which it sends only when a fake scenario is set.
import { ENGINE_NUDGE } from "@asf/core";
import fs from "node:fs";
import http from "node:http";
import path from "node:path";

type Step =
  | { write: string; content: string }
  | { append: string; content: string }
  | { bash: string; allowFail?: boolean }
  | { asf: string[]; allowFail?: boolean }
  | { text: string }
  | { todo: { content: string; status: string; activeForm?: string }[] }
  | { sleep: number }
  | { hang: true }
  | { usageLimit: { inSeconds?: number } }
  | { notLoggedIn: true }
  | { exit: number }
  | { expectPrompt: string }
  | { rateLimit: { status: string; inSeconds?: number } }
  /** Like a weaker model: a reply with text and no tool call (the engine nudges once). */
  | { say: string }
  /** Any tool call, as a model might name it ("read_file", "bash", …). */
  | { call: { name: string; input: Record<string, unknown> } };

interface Script {
  steps: Step[];
  exitCode?: number;
  resultText?: string;
}

/** One reply of the fake model: a tool call, a final text, or an HTTP error. */
type Action =
  | { kind: "tool"; name: string; input: Record<string, unknown>; text?: string; delayMs?: number }
  | { kind: "final"; text: string; delayMs?: number }
  | { kind: "say"; text: string; delayMs?: number }
  | { kind: "error"; status: number; body: string; headers?: Record<string, string>; delayMs?: number }
  | { kind: "hang" };

export interface FakeLlm {
  url: string;
  close(): Promise<void>;
}

const shq = (s: string) => `'${s.replace(/'/g, `'\\''`)}'`;

function expand(s: string, ctx: Record<string, string>): string {
  // Unknown variables stay as they are, so bash expands them from the agent's environment.
  return s.replace(/\$\{([A-Z_][A-Z0-9_]*)\}/g, (m, k: string) => (ctx[k] !== undefined ? ctx[k]! : m));
}

function actionsFor(script: Script, ctx: Record<string, string>): { actions: Action[]; expect: string[] } {
  const actions: Action[] = [];
  const expect: string[] = [];
  let text: string[] = [];
  let delay = 0;
  const push = (a: Action) => {
    if (a.kind === "tool" && text.length) a.text = text.join("\n");
    if (a.kind !== "hang" && delay) a.delayMs = delay;
    text = [];
    delay = 0;
    actions.push(a);
  };
  for (const s of script.steps) {
    if ("expectPrompt" in s) expect.push(expand(s.expectPrompt, ctx));
    else if ("text" in s) text.push(expand(s.text, ctx));
    else if ("sleep" in s) delay += s.sleep;
    else if ("write" in s) push({ kind: "tool", name: "Write", input: { file_path: expand(s.write, ctx), content: expand(s.content, ctx) } });
    else if ("append" in s) push({ kind: "tool", name: "Bash", input: { command: `printf '%s' ${shq(expand(s.content, ctx))} >> ${shq(expand(s.append, ctx))}` } });
    else if ("bash" in s) push({ kind: "tool", name: "Bash", input: { command: expand(s.bash, ctx) } });
    else if ("asf" in s) push({ kind: "tool", name: "Bash", input: { command: `asf ${s.asf.map((a) => shq(expand(a, ctx))).join(" ")}` } });
    else if ("todo" in s) push({ kind: "tool", name: "TodoWrite", input: { todos: s.todo } });
    else if ("say" in s) push({ kind: "say", text: expand(s.say, ctx) });
    else if ("call" in s)
      push({ kind: "tool", name: s.call.name, input: Object.fromEntries(Object.entries(s.call.input).map(([k, v]) => [k, typeof v === "string" ? expand(v, ctx) : v])) });
    else if ("hang" in s) push({ kind: "hang" });
    else if ("usageLimit" in s)
      push({ kind: "error", status: 429, body: JSON.stringify({ error: { message: "Rate limit reached" } }), headers: { "retry-after": String(s.usageLimit.inSeconds ?? 3600) } });
    else if ("rateLimit" in s) {
      if (s.rateLimit.status === "rejected") push({ kind: "error", status: 429, body: "{}", headers: { "retry-after": String(s.rateLimit.inSeconds ?? 60) } });
    } else if ("notLoggedIn" in s) push({ kind: "error", status: 401, body: JSON.stringify({ error: { message: "Invalid API Key" } }) });
    else if ("exit" in s) push({ kind: "error", status: 400, body: JSON.stringify({ error: { message: `fake-llm exiting with ${s.exit}` } }) });
  }
  if (script.exitCode) push({ kind: "error", status: 400, body: JSON.stringify({ error: { message: script.resultText ?? `fake-llm exit ${script.exitCode}` } }) });
  else push({ kind: "final", text: [...text, script.resultText ?? "Done."].join("\n") });
  return { actions, expect };
}

export async function startFakeLlm(opts: { scenarioFile: string; stateDir: string }): Promise<FakeLlm> {
  /** Which script each run got (array scenarios advance once per run, like fake-claude per process). */
  const scriptOfRun = new Map<string, Script>();
  const counters = new Map<string, number>();
  const lastRequest = new Map<string, number>();
  fs.mkdirSync(opts.stateDir, { recursive: true });

  const pickScript = (h: Record<string, string>, prompt: string): Script => {
    const run = h["x-asf-run"] ?? "";
    const known = scriptOfRun.get(run);
    if (known) return known;
    const scenario = JSON.parse(fs.readFileSync(opts.scenarioFile, "utf8")) as Record<string, Script | Script[]>;
    const { role, task, mode, resume } = { role: h["x-asf-role"] ?? "", task: h["x-asf-task"] ?? "", mode: h["x-asf-mode"] ?? "", resume: Boolean(h["x-asf-resume"]) };
    const base = [task && `task:${task}:${mode}`, task && `task:${task}:${role}`, task && `task:${task}`, `${role}:${mode}`, role, "default"].filter(Boolean) as string[];
    const keys = [...(resume ? base.map((k) => `${k}:resume`) : []), ...base];
    const key = keys.find((k) => scenario[k] !== undefined);
    let script: Script = { steps: [{ text: "Nothing to do in this scenario." }] };
    if (key) {
      const v = scenario[key]!;
      if (Array.isArray(v)) {
        const i = counters.get(key) ?? 0;
        counters.set(key, i + 1);
        script = v[Math.min(i, v.length - 1)]!;
      } else script = v;
    }
    scriptOfRun.set(run, script);
    fs.appendFileSync(path.join(opts.stateDir, "invocations.jsonl"), `${JSON.stringify({ engine: true, run, role, task, mode, resume, prompt: prompt.slice(0, 4000), at: Date.now() })}\n`);
    return script;
  };

  const server = http.createServer((req, res) => {
    const send = (status: number, body: unknown, headers: Record<string, string> = {}) => {
      res.writeHead(status, { "content-type": "application/json", ...headers });
      res.end(typeof body === "string" ? body : JSON.stringify(body));
    };
    const auth = String(req.headers.authorization ?? "");
    // Test keys: "bad…" is rejected, "limited…" is always rate limited.
    if (/^Bearer bad/.test(auth)) return send(401, { error: { message: "Invalid API Key" } });
    if (/^Bearer limited/.test(auth)) return send(429, { error: { message: "Rate limit reached" } }, { "retry-after": "3600" });
    if (req.method === "GET" && /\/models$/.test(req.url ?? "")) return send(200, { data: [{ id: "fake-model" }, { id: "fake-fast" }] });
    if (req.method !== "POST" || !/\/chat\/completions$/.test(req.url ?? "")) return send(404, { error: { message: "not found" } });
    let raw = "";
    req.on("data", (c: Buffer) => {
      raw += c.toString();
    });
    req.on("end", () => {
      let body: any;
      try {
        body = JSON.parse(raw);
      } catch {
        return send(400, { error: { message: "bad json" } });
      }
      // Real-provider behaviour the engine must cope with:
      // "small…" keys allow 8000 tokens per request (like Groq's free tier for some models);
      const requested = Math.ceil(raw.length / 4);
      if (/^Bearer small/.test(auth) && requested > 8000)
        return send(413, {
          error: { message: `Request too large for model \`${body.model}\` on tokens per minute (TPM): Limit 8000, Requested ${requested}, please reduce your message size and try again.` },
        });
      // "minute…" keys allow one request per second (a per-minute limit, scaled down);
      if (/^Bearer minute/.test(auth)) {
        const last = lastRequest.get(auth) ?? 0;
        if (Date.now() - last < 1000) return send(429, { error: { message: "Rate limit reached: requests per minute" } }, { "retry-after": "1" });
        lastRequest.set(auth, Date.now());
      }
      // and models named "no-tools…" cannot call tools.
      if (String(body.model).startsWith("no-tools")) return send(400, { error: { message: `${body.model} does not support tools` } });
      const messages: any[] = body.messages ?? [];
      // The engine's nudge is not a new prompt: the script carries on where it was.
      const lastUser = messages.map((m) => (m.role === "user" && m.content === ENGINE_NUDGE ? "nudge" : m.role)).lastIndexOf("user");
      const prompt = String(messages[lastUser]?.content ?? "");
      const h: Record<string, string> = {};
      for (const [k, v] of Object.entries(req.headers)) if (k.startsWith("x-asf-")) h[k] = String(v);
      const ctx = { ASF_TASK: h["x-asf-task"] ?? "", ASF_ROLE: h["x-asf-role"] ?? "", ASF_MODE: h["x-asf-mode"] ?? "", ASK_ID: /M-\d{4}/.exec(prompt)?.[0] ?? "", MERGE_BRANCH: /Branch to merge: `([^`]+)`/.exec(prompt)?.[1] ?? "" };
      const { actions, expect } = actionsFor(pickScript(h, prompt), ctx);
      const missing = expect.find((x) => !prompt.includes(x));
      if (missing) return send(400, { error: { message: `fake-llm: prompt did not contain "${missing}"` } });
      const step = messages.slice(lastUser + 1).filter((m) => m.role === "assistant").length;
      const a = actions[Math.min(step, actions.length - 1)]!;
      if (a.kind === "hang") return; // never answer; the engine aborts the request when the run is killed
      const reply = () => {
        if (a.kind === "error") return send(a.status, a.body, a.headers);
        const usage = { prompt_tokens: 1000, completion_tokens: 200, total_tokens: 1200 };
        const message =
          a.kind === "tool"
            ? { role: "assistant", content: a.text ?? null, tool_calls: [{ id: `call_${step}_${Date.now()}`, type: "function", function: { name: a.name, arguments: JSON.stringify(a.input) } }] }
            : { role: "assistant", content: a.text };
        send(200, { id: `chatcmpl-${step}`, object: "chat.completion", model: body.model, choices: [{ index: 0, message, finish_reason: a.kind === "tool" ? "tool_calls" : "stop" }], usage });
      };
      if (a.delayMs) setTimeout(reply, a.delayMs);
      else reply();
    });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const port = (server.address() as { port: number }).port;
  return {
    url: `http://127.0.0.1:${port}/v1`,
    close: () =>
      new Promise<void>((resolve) => {
        server.closeAllConnections();
        server.close(() => resolve());
      }),
  };
}
