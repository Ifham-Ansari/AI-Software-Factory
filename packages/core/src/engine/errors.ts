// What a failed request to an OpenAI-compatible provider means for the engine. Pure, so every provider's
// rate-limit format is unit tested.

export type ProviderErrorKind = "auth" | "limited" | "context" | "retry" | "fatal";

export interface ProviderError {
  kind: ProviderErrorKind;
  /** Epoch ms when a rate-limited key may be used again. */
  resetsAt?: number;
  /** For a request that is too large: the token limit the provider reported, when it said one. */
  limit?: number;
  message: string;
}

const DEFAULT_COOLDOWN_MS = 60_000;

/**
 * The token limit in a "request too large" error: Groq's "tokens per minute (TPM): Limit 8000, Requested 13419",
 * OpenAI's "maximum context length is 8192 tokens", or "context window of 32768 tokens".
 */
export function reportedTokenLimit(text: string): number | undefined {
  const m =
    /\bLimit\s*:?\s*(\d{3,})\b/i.exec(text) ??
    /maximum context length is\s*(\d{3,})/i.exec(text) ??
    /context (?:length|window)(?: of| is)?\s*(\d{3,})/i.exec(text) ??
    /max(?:imum)?[_ ]tokens?[^\d]{0,20}(\d{3,})/i.exec(text);
  return m ? Number(m[1]) : undefined;
}

/** "2m59.56s", "1h2m", "30s", "750ms", "12" (seconds) → milliseconds. */
export function parseDurationMs(s: string): number | undefined {
  const t = s.trim();
  if (/^\d+(\.\d+)?$/.test(t)) return Math.round(Number(t) * 1000);
  const re = /(\d+(?:\.\d+)?)(ms|h|m|s)/g;
  let total = 0;
  let matched = false;
  for (const m of t.matchAll(re)) {
    matched = true;
    const n = Number(m[1]);
    total += m[2] === "h" ? n * 3_600_000 : m[2] === "m" ? n * 60_000 : m[2] === "s" ? n * 1000 : n;
  }
  return matched ? Math.round(total) : undefined;
}

function header(headers: Record<string, string>, name: string): string | undefined {
  const k = Object.keys(headers).find((h) => h.toLowerCase() === name);
  return k ? headers[k] : undefined;
}

/** When a 429 says the key may be used again, from the formats providers use. */
export function rateLimitResetAt(headers: Record<string, string>, body: string, now = Date.now()): number {
  const retryAfter = header(headers, "retry-after");
  if (retryAfter) {
    const ms = parseDurationMs(retryAfter);
    if (ms !== undefined) return now + ms;
    const date = Date.parse(retryAfter);
    if (!Number.isNaN(date)) return date;
  }
  // Groq / OpenAI style: x-ratelimit-reset-requests: 2m59.56s, x-ratelimit-reset-tokens: 7.66s.
  const resets = ["x-ratelimit-reset-requests", "x-ratelimit-reset-tokens"]
    .map((h) => header(headers, h))
    .filter((v): v is string => Boolean(v))
    .map(parseDurationMs)
    .filter((v): v is number => v !== undefined);
  if (resets.length) return now + Math.max(...resets);
  // OpenRouter style: X-RateLimit-Reset in epoch milliseconds (or seconds).
  const reset = header(headers, "x-ratelimit-reset");
  if (reset && /^\d+$/.test(reset)) {
    const n = Number(reset);
    return n > 1e12 ? n : n > 1e9 ? n * 1000 : now + n * 1000;
  }
  // Gemini style, in the body: "retryDelay": "33s".
  const delay = /"retryDelay"\s*:\s*"([^"]+)"/.exec(body)?.[1];
  if (delay) {
    const ms = parseDurationMs(delay);
    if (ms !== undefined) return now + ms;
  }
  return now + DEFAULT_COOLDOWN_MS;
}

function bodyMessage(body: string): string {
  try {
    const j = JSON.parse(body) as any;
    const e = Array.isArray(j) ? j[0]?.error : j?.error;
    const m = typeof e === "string" ? e : (e?.message ?? j?.message);
    if (m) return String(m);
  } catch {
    /* not JSON */
  }
  return body.trim().slice(0, 300) || "no details";
}

const CONTEXT_RE = /context[_ ]length|context window|maximum context|too many tokens|prompt is too long|reduce the length|request too large|input.{0,20}too long/i;
const QUOTA_RE = /quota|rate[_ -]?limit|resource[_ ]exhausted|too many requests|credits/i;

/**
 * The model is not free on this account: it needs credits or a paid plan. Waiting does not help, so it is not a
 * rate limit (OpenRouter's "requires more credits", Z.ai's "Insufficient balance or no resource package").
 * OpenRouter's daily free cap ("free-models-per-day … Add 10 credits to unlock …") is a limit, and does not match.
 */
const PAYMENT_RE = /requires more credits|insufficient (account )?balance|no resource package|payment required|not available on (the|your) free (tier|plan)/i;

export function classifyProviderError(status: number, headers: Record<string, string>, body: string, now = Date.now()): ProviderError {
  const message = `HTTP ${status}: ${bodyMessage(body)}`;
  if (status === 401 || status === 403) return { kind: "auth", message };
  // A paid model on a free account fails the same way every time: rule the model out instead of waiting.
  if (status === 402 || PAYMENT_RE.test(body)) return { kind: "fatal", message: `${message} (this model is not free on this account)` };
  if (status === 429) return { kind: "limited", resetsAt: rateLimitResetAt(headers, body, now), message };
  if (status === 413 || CONTEXT_RE.test(body)) return { kind: "context", limit: reportedTokenLimit(body), message };
  // Some providers answer a used-up free quota with 400 plus a quota message.
  if (status === 400 && QUOTA_RE.test(body)) return { kind: "limited", resetsAt: rateLimitResetAt(headers, body, now), message };
  if (status === 408 || status >= 500 || status === 0) return { kind: "retry", message };
  return { kind: "fatal", message };
}
