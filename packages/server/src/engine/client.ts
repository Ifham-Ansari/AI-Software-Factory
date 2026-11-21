import { classifyProviderError, type ChatMessage, type ProviderError, type ToolCallMsg, type ToolDef } from "@asf/core";

// A minimal client for OpenAI-compatible /chat/completions. No SDK: every free provider speaks this format.
// Keys are only ever put in the Authorization header and scrubbed from any error text.

export interface ChatUsage {
  input: number;
  output: number;
  cacheRead: number;
}

export type ChatResult =
  | { ok: true; message: { content: string | null; tool_calls?: ToolCallMsg[] }; usage: ChatUsage; finishReason: string }
  | { ok: false; error: ProviderError; aborted?: boolean };

export interface ChatRequest {
  baseUrl: string;
  apiKey: string;
  model: string;
  messages: ChatMessage[];
  tools: ToolDef[];
  signal: AbortSignal;
  timeoutMs?: number;
  /** Only for the test double (fake-llm): which run is asking. Never set for real providers. */
  testHeaders?: Record<string, string>;
}

function scrub(text: string, key: string): string {
  return key && key.length >= 6 ? text.split(key).join("••••") : text;
}

export function chatUrl(baseUrl: string): string {
  return `${baseUrl.replace(/\/+$/, "")}/chat/completions`;
}

export async function chatCompletion(req: ChatRequest): Promise<ChatResult> {
  const timeout = AbortSignal.timeout(req.timeoutMs ?? 300_000);
  const signal = AbortSignal.any([req.signal, timeout]);
  let res: Response;
  try {
    res = await fetch(chatUrl(req.baseUrl), {
      method: "POST",
      headers: { "content-type": "application/json", ...(req.apiKey ? { authorization: `Bearer ${req.apiKey}` } : {}), ...req.testHeaders },
      body: JSON.stringify({ model: req.model, messages: req.messages, tools: req.tools, tool_choice: "auto" }),
      signal,
    });
  } catch (e) {
    if (req.signal.aborted) return { ok: false, aborted: true, error: { kind: "fatal", message: "aborted" } };
    const msg = timeout.aborted ? "request timed out" : (e as Error).message;
    return { ok: false, error: { kind: "retry", message: scrub(`network error: ${msg}`, req.apiKey) } };
  }
  const text = await res.text().catch(() => "");
  if (!res.ok) {
    const headers: Record<string, string> = {};
    res.headers.forEach((v, k) => {
      headers[k] = v;
    });
    const err = classifyProviderError(res.status, headers, text);
    return { ok: false, error: { ...err, message: scrub(err.message, req.apiKey) } };
  }
  let j: any;
  try {
    j = JSON.parse(text);
  } catch {
    return { ok: false, error: { kind: "retry", message: "the provider sent a response that is not JSON" } };
  }
  // Some providers report errors with HTTP 200.
  if (j?.error) {
    const err = classifyProviderError(Number(j.error.code) || 500, {}, JSON.stringify(j));
    return { ok: false, error: { ...err, message: scrub(err.message, req.apiKey) } };
  }
  const choice = j?.choices?.[0];
  if (!choice?.message) return { ok: false, error: { kind: "retry", message: "the provider sent no message" } };
  const u = j.usage ?? {};
  const cached = Number(u.prompt_tokens_details?.cached_tokens ?? 0);
  return {
    ok: true,
    message: { content: choice.message.content ?? null, tool_calls: choice.message.tool_calls?.length ? choice.message.tool_calls : undefined },
    usage: { input: Math.max(0, Number(u.prompt_tokens ?? 0) - cached), output: Number(u.completion_tokens ?? 0), cacheRead: cached },
    finishReason: String(choice.finish_reason ?? ""),
  };
}

/** List a provider's models (free: no tokens used). Used to test a key and to fill the model pickers. */
export async function listModels(baseUrl: string, apiKey: string, timeoutMs = 15_000): Promise<{ ok: true; models: string[] } | { ok: false; error: ProviderError }> {
  try {
    const res = await fetch(`${baseUrl.replace(/\/+$/, "")}/models`, {
      headers: apiKey ? { authorization: `Bearer ${apiKey}` } : {},
      signal: AbortSignal.timeout(timeoutMs),
    });
    const text = await res.text();
    if (!res.ok) {
      const err = classifyProviderError(res.status, {}, text);
      return { ok: false, error: { ...err, message: scrub(err.message, apiKey) } };
    }
    const j = JSON.parse(text) as any;
    const list: any[] = Array.isArray(j?.data) ? j.data : Array.isArray(j?.models) ? j.models : [];
    const models = list.map((m) => String(m.id ?? m.name ?? "").replace(/^models\//, "")).filter(Boolean).sort();
    return { ok: true, models };
  } catch (e) {
    return { ok: false, error: { kind: "retry", message: scrub(`could not reach ${baseUrl}: ${(e as Error).message}`, apiKey) } };
  }
}
