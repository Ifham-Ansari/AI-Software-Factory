// Question batches (`asf ask @human --batch`), in the one shape the dashboard and the answer formatter read.
// Agents write the file themselves, and models differ in the details: options as a list of {key, label}, a list of
// {label, value}, plain strings, or a map {"A": "…"}; "recommended" or "recommendation"; "why_it_matters" or "why".
// Every batch goes through normalizeBatch when it is stored and when it is read, so none can break the Questions
// screen. Pure.

export interface BatchOption {
  key: string;
  label: string;
}

export interface BatchQuestion {
  id: string;
  question: string;
  topic?: string;
  options?: BatchOption[];
  recommended?: string;
  why_it_matters?: string;
}

export interface Batch {
  intro?: string;
  questions: BatchQuestion[];
}

const LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

const str = (v: unknown): string | undefined => (typeof v === "string" && v.trim() ? v.trim() : typeof v === "number" ? String(v) : undefined);
const first = (o: Record<string, unknown>, keys: string[]): string | undefined => {
  for (const k of keys) {
    const v = str(o[k]);
    if (v) return v;
  }
  return undefined;
};

function normalizeOptions(raw: unknown): BatchOption[] {
  const out: BatchOption[] = [];
  const push = (key: string, label: string) => {
    // A label that repeats its key ("A — Ledger: …", "B: …") reads better without it.
    const clean = label.replace(new RegExp(`^${key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*[—–:.)-]\\s*`), "");
    out.push({ key, label: clean || label });
  };
  if (Array.isArray(raw)) {
    raw.forEach((o, i) => {
      if (typeof o === "string" || typeof o === "number") push(LETTERS[i] ?? String(i + 1), String(o));
      else if (o && typeof o === "object") {
        const r = o as Record<string, unknown>;
        const key = first(r, ["key", "value", "id", "option", "letter"]) ?? LETTERS[i] ?? String(i + 1);
        const label = first(r, ["label", "text", "title", "name", "description", "value"]) ?? key;
        const detail = first(r, ["description", "detail", "details"]);
        push(key, detail && detail !== label ? `${label}: ${detail}` : label);
      }
    });
  } else if (raw && typeof raw === "object") {
    for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
      if (typeof v === "string" || typeof v === "number") push(k, String(v));
      else if (v && typeof v === "object") push(k, first(v as Record<string, unknown>, ["label", "text", "title", "description"]) ?? k);
    }
  }
  // Keys must be unique for the radio buttons; keep the first of any duplicates.
  return out.filter((o, i) => out.findIndex((x) => x.key === o.key) === i);
}

/** Which option a recommendation means: its key, its label, or a sentence that starts with its key ("C — Bloom. …"). */
function matchRecommendation(rec: string, options: BatchOption[]): { key?: string; rest?: string } {
  if (!options.length) return { key: rec };
  const exact = options.find((o) => o.key === rec) ?? options.find((o) => o.key.toLowerCase() === rec.toLowerCase() || o.label.toLowerCase() === rec.toLowerCase());
  if (exact) return { key: exact.key };
  for (const o of options) {
    // The key, then a separator ("C — …", "C: …", "C.") or nothing: "A strong choice is C" does not mean A.
    const m = new RegExp(`^${o.key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?:\\s*[—–:.)-]|$)\\s*(.*)$`, "s").exec(rec);
    if (m) return { key: o.key, rest: m[1]?.replace(/^[^.]*\.\s*/, "").trim() || undefined };
  }
  return {};
}

export function normalizeBatch(raw: unknown): Batch {
  const b = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  const list = Array.isArray(raw) ? raw : Array.isArray(b.questions) ? b.questions : b.question && typeof b.question === "object" ? [b.question] : [];
  const questions: BatchQuestion[] = [];
  list.forEach((item, i) => {
    if (typeof item === "string") {
      questions.push({ id: `Q${i + 1}`, question: item });
      return;
    }
    if (!item || typeof item !== "object") return;
    const q = item as Record<string, unknown>;
    const question = first(q, ["question", "text", "prompt", "title", "topic"]);
    if (!question) return;
    const options = normalizeOptions(q.options ?? q.choices ?? q.answers);
    const recRaw = first(q, ["recommended", "recommendation", "recommend", "default", "suggested"]);
    const rec = recRaw ? matchRecommendation(recRaw, options) : {};
    const why = first(q, ["why_it_matters", "why", "reason", "rationale", "explanation"]) ?? rec.rest;
    const topic = first(q, ["topic", "title"]);
    questions.push({
      id: first(q, ["id", "key", "name"]) ?? `Q${i + 1}`,
      question,
      ...(topic && topic !== question ? { topic } : {}),
      ...(options.length ? { options } : {}),
      ...(rec.key ? { recommended: rec.key } : {}),
      ...(why ? { why_it_matters: why } : {}),
    });
  });
  const intro = first(b, ["intro", "title", "summary"]);
  return { ...(intro ? { intro } : {}), questions };
}
