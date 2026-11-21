import { describe, expect, it } from "vitest";
import { guardDecision } from "../guard.ts";
import { compactMessages, estimateTokens, type ChatMessage } from "./compact.ts";
import { classifyProviderError, parseDurationMs, rateLimitResetAt, reportedTokenLimit } from "./errors.ts";
import { pickKey, type PoolKey } from "./pool.ts";
import { maskKey, parseModelRef } from "./providers.ts";
import { engineCallId, normalizeToolCall } from "./tools.ts";

const NOW = 1_900_000_000_000;

describe("provider errors", () => {
  it("parses the duration formats providers use", () => {
    expect(parseDurationMs("2m59.56s")).toBe(179_560);
    expect(parseDurationMs("7.66s")).toBe(7660);
    expect(parseDurationMs("1h2m")).toBe(3_720_000);
    expect(parseDurationMs("750ms")).toBe(750);
    expect(parseDurationMs("12")).toBe(12_000);
    expect(parseDurationMs("soon")).toBeUndefined();
  });

  it("reads each provider's rate-limit reset", () => {
    expect(rateLimitResetAt({ "Retry-After": "30" }, "", NOW)).toBe(NOW + 30_000);
    // Groq: the later of the request and token resets.
    expect(rateLimitResetAt({ "x-ratelimit-reset-requests": "2m0s", "x-ratelimit-reset-tokens": "7.5s" }, "", NOW)).toBe(NOW + 120_000);
    // OpenRouter: epoch milliseconds.
    expect(rateLimitResetAt({ "x-ratelimit-reset": String(NOW + 5000) }, "", NOW)).toBe(NOW + 5000);
    // Gemini: retryDelay in the body.
    expect(rateLimitResetAt({}, '{"error":{"details":[{"retryDelay":"33s"}]}}', NOW)).toBe(NOW + 33_000);
    expect(rateLimitResetAt({}, "", NOW)).toBe(NOW + 60_000);
  });

  it("reads the token limit a provider reports for a request that is too large", () => {
    const groq =
      '{"error":{"message":"Request too large for model `openai/gpt-oss-120b` in organization `org_x` service tier `on_demand` on tokens per minute (TPM): Limit 8000, Requested 13419, please reduce your message size and try again."}}';
    expect(classifyProviderError(413, {}, groq)).toMatchObject({ kind: "context", limit: 8000 });
    expect(reportedTokenLimit("This model's maximum context length is 8192 tokens.")).toBe(8192);
    expect(reportedTokenLimit("exceeds the context window of 32768 tokens")).toBe(32768);
    expect(reportedTokenLimit("prompt is too long")).toBeUndefined();
  });

  it("classifies failures", () => {
    expect(classifyProviderError(401, {}, '{"error":{"message":"Invalid API Key"}}')).toMatchObject({ kind: "auth", message: "HTTP 401: Invalid API Key" });
    expect(classifyProviderError(429, { "retry-after": "10" }, "", NOW)).toMatchObject({ kind: "limited", resetsAt: NOW + 10_000 });
    expect(classifyProviderError(400, {}, '{"error":{"message":"This model\'s maximum context length is 8192 tokens"}}').kind).toBe("context");
    expect(classifyProviderError(400, {}, '{"error":{"message":"You exceeded your current quota"}}').kind).toBe("limited");
    expect(classifyProviderError(503, {}, "overloaded").kind).toBe("retry");
    expect(classifyProviderError(400, {}, '{"error":{"message":"tools are not supported by this model"}}').kind).toBe("fatal");
  });
});

describe("key pool", () => {
  const keys: PoolKey[] = [
    { id: "a", provider: "groq", label: "Ayesha" },
    { id: "b", provider: "groq", label: "Bilal" },
    { id: "c", provider: "gemini", label: "Sara" },
  ];

  it("spreads requests over the team's keys for the first model", () => {
    const pick = pickKey(["groq:llama", "gemini:flash"], keys, { a: { lastUsed: NOW - 10 }, b: { lastUsed: NOW - 100 } }, NOW);
    expect(pick).toMatchObject({ ok: true, key: { id: "b" }, provider: "groq", model: "llama" });
  });

  it("skips cooling and rejected keys, then falls back to the next model", () => {
    const pick = pickKey(["groq:llama", "gemini:flash"], [{ ...keys[0]!, invalid: "HTTP 401" }, keys[1]!, keys[2]!], { b: { cooldownUntil: NOW + 1000 } }, NOW);
    expect(pick).toMatchObject({ ok: true, key: { id: "c" }, model: "flash" });
  });

  it("reports the earliest reset when everything is cooling down", () => {
    const pick = pickKey(["groq:llama"], keys, { a: { cooldownUntil: NOW + 5000 }, b: { cooldownUntil: NOW + 2000 } }, NOW);
    expect(pick).toMatchObject({ ok: false, reason: "limited", resetsAt: NOW + 2000 });
  });

  it("says so when no key can serve the chosen models", () => {
    expect(pickKey(["mistral:small"], keys, {}, NOW)).toMatchObject({ ok: false, reason: "no_keys" });
    expect(pickKey([], keys, {}, NOW)).toMatchObject({ ok: false, reason: "no_keys" });
  });

  it("parses model refs whose ids contain colons", () => {
    expect(parseModelRef("openrouter:meta-llama/llama-3.3-70b-instruct:free")).toEqual({ provider: "openrouter", model: "meta-llama/llama-3.3-70b-instruct:free" });
    expect(parseModelRef("ollama:qwen2.5-coder:32b")).toEqual({ provider: "ollama", model: "qwen2.5-coder:32b" });
    expect(parseModelRef("sonnet")).toBeNull();
    expect(maskKey("gsk_abcdefghijklmnop1234")).toBe("••••1234");
  });
});

describe("compaction", () => {
  const step = (i: number, size: number): ChatMessage[] => [
    { role: "assistant", content: null, tool_calls: [{ id: `c${i}`, type: "function", function: { name: "Read", arguments: `{"file_path":"f${i}"}` } }] },
    { role: "tool", tool_call_id: `c${i}`, content: "x".repeat(size) },
  ];

  it("leaves a small conversation alone", () => {
    const m: ChatMessage[] = [{ role: "user", content: "task" }, ...step(1, 100)];
    expect(compactMessages(m, 10_000)).toBe(m);
  });

  it("stubs old tool output first, keeping the latest results", () => {
    const m: ChatMessage[] = [{ role: "user", content: "task" }, ...Array.from({ length: 10 }, (_, i) => step(i, 4000)).flat()];
    const out = compactMessages(m, 8000);
    const tools = out.filter((x) => x.role === "tool");
    expect(tools).toHaveLength(10);
    expect(tools.slice(-6).every((t) => t.content.length === 4000)).toBe(true);
    expect(tools[0]!.content).toMatch(/trimmed/);
  });

  it("drops the oldest steps whole when stubs are not enough, never splitting a call from its result", () => {
    const m: ChatMessage[] = [{ role: "user", content: "task" }, ...Array.from({ length: 10 }, (_, i) => step(i, 4000)).flat()];
    const out = compactMessages(m, 2500, 6);
    expect(estimateTokens(out)).toBeLessThan(estimateTokens(m));
    expect(out[0]).toMatchObject({ role: "user" });
    expect((out[0] as { content: string }).content).toMatch(/earlier steps were removed/);
    const callIds = out.flatMap((x) => (x.role === "assistant" ? (x.tool_calls ?? []).map((c) => c.id) : []));
    const resultIds = out.flatMap((x) => (x.role === "tool" ? [x.tool_call_id] : []));
    expect(resultIds).toEqual(callIds);
  });
});

describe("tool calls from weaker models", () => {
  it("maps common tool and argument names to the real ones", () => {
    expect(normalizeToolCall("read_file", { path: "a.ts" })).toEqual({ name: "Read", input: { file_path: "a.ts" } });
    expect(normalizeToolCall("bash", { cmd: "ls" })).toEqual({ name: "Bash", input: { command: "ls" } });
    expect(normalizeToolCall("str_replace", { path: "a", old_str: "x", new_str: "y" })).toEqual({ name: "Edit", input: { file_path: "a", old_string: "x", new_string: "y" } });
    expect(normalizeToolCall("WRITE", { file_path: "a", text: "t" })).toEqual({ name: "Write", input: { file_path: "a", content: "t" } });
    // The real name wins over an alias when both are given; unknown tools pass through.
    expect(normalizeToolCall("Read", { file_path: "a", path: "b" }).input).toEqual({ file_path: "a", path: "b" });
    expect(normalizeToolCall("fly", { x: 1 })).toEqual({ name: "fly", input: { x: 1 } });
  });

  it("makes call ids every provider accepts (9 letters and digits)", () => {
    expect(engineCallId(3, 0)).toMatch(/^[a-zA-Z0-9]{9}$/);
    expect(engineCallId(12345, 7)).toBe("c12345x07");
    expect(engineCallId(4, 1)).not.toBe(engineCallId(5, 1));
  });
});

describe("guard and the engine's keys", () => {
  const ctx = { role: "backend" as const, agent: "backend-1", worktree: "/w/app", writable: ["src/**"], branch: "", composeProject: "c", homeDir: "/home/u", direct: true };
  it("never lets an agent read or write the team's API keys", () => {
    expect(guardDecision({ tool_name: "Read", tool_input: { file_path: "/home/u/.asf/keys.json" } }, ctx).allow).toBe(false);
    expect(guardDecision({ tool_name: "Bash", tool_input: { command: "cat ~/.asf/keys.json" } }, ctx).allow).toBe(false);
    expect(guardDecision({ tool_name: "Bash", tool_input: { command: "type %USERPROFILE%\\.asf\\key-usage.json" } }, ctx).allow).toBe(false);
    expect(guardDecision({ tool_name: "Bash", tool_input: { command: "ls .asf/sessions" } }, ctx).allow).toBe(false);
    expect(guardDecision({ tool_name: "Read", tool_input: { file_path: "/w/app/src/keys.json" } }, ctx).allow).toBe(true);
  });
});
