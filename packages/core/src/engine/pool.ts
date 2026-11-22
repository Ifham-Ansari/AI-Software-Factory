import { parseModelRef } from "./providers.ts";

// Which key and model the next request uses. Teammates add their own keys on the host computer; requests spread
// over every healthy key. A limit cools down what it applies to until its reset: one model of a key where the
// provider limits each model separately (Groq, Gemini), or the whole key where the limit is for the account
// (OpenRouter's daily free cap). A key the provider rejects is marked invalid. Pure: the server keeps the state
// and calls this before each request.

export interface PoolKey {
  id: string;
  /** Provider id (groq, gemini, …) or "custom". */
  provider: string;
  /** Whose key it is, shown to the team. */
  label: string;
  /** Set when the provider rejected the key (401/403). */
  invalid?: string | null;
}

export interface PoolKeyState {
  /** Epoch ms until which the whole key is rate limited. */
  cooldownUntil?: number;
  /** Epoch ms until which one model of the key is rate limited, by model id. */
  models?: Record<string, number>;
  /** Epoch ms of the last request, so load spreads over keys. */
  lastUsed?: number;
}

/** When the key can serve this model again (now or earlier: it can). */
export function readyAt(state: PoolKeyState | undefined, model: string): number {
  return Math.max(state?.cooldownUntil ?? 0, state?.models?.[model] ?? 0);
}

export type PoolPick =
  | { ok: true; key: PoolKey; provider: string; model: string; ref: string }
  | { ok: false; reason: "no_keys"; message: string }
  | { ok: false; reason: "limited"; resetsAt: number; message: string };

function matches(key: PoolKey, provider: string): boolean {
  return key.provider === provider || key.id === provider;
}

/** Pick a key for the first model in `chain` that has a usable one. */
export function pickKey(chain: string[], keys: PoolKey[], state: Record<string, PoolKeyState>, now = Date.now()): PoolPick {
  let earliest = Number.POSITIVE_INFINITY;
  const refs = chain.map((ref) => ({ ref, parsed: parseModelRef(ref) })).filter((r) => r.parsed);
  if (!refs.length)
    return { ok: false, reason: "no_keys", message: "No model to use: add a working API key (its best model is then picked automatically), or choose models in Settings." };
  for (const { ref, parsed } of refs) {
    const usable = keys.filter((k) => matches(k, parsed!.provider) && !k.invalid);
    const ready = usable.filter((k) => readyAt(state[k.id], parsed!.model) <= now);
    for (const k of usable) earliest = Math.min(earliest, Math.max(readyAt(state[k.id], parsed!.model), now));
    if (ready.length) {
      ready.sort((a, b) => (state[a.id]?.lastUsed ?? 0) - (state[b.id]?.lastUsed ?? 0));
      return { ok: true, key: ready[0]!, provider: parsed!.provider, model: parsed!.model, ref };
    }
  }
  if (Number.isFinite(earliest)) {
    return { ok: false, reason: "limited", resetsAt: earliest, message: "Every API key for the chosen models has hit its limit" };
  }
  const providers = [...new Set(refs.map((r) => r.parsed!.provider))].join(", ");
  return { ok: false, reason: "no_keys", message: `No working API key for ${providers}. Add or fix one on the Keys screen (or \`asf keys add\`).` };
}
