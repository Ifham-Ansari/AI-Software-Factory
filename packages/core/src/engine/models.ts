import { providerPreset } from "./providers.ts";

// Picking models for agent work from a provider's own GET /models list (model ids are only hard-coded as a
// fallback: free models change too often). A best guess from what the list says (tool support, free or paid,
// context size) and what the id says (size, family, tier). The owner's own choice in Settings always comes first.

export interface ModelInfo {
  id: string;
  /** Tokens of context, when the provider says. */
  contextWindow?: number;
  /** Whether the model can call tools (agents need it), when the provider says. */
  tools?: boolean;
  /** Free to use, when the provider says (OpenRouter's pricing, or an id ending in ":free"). */
  free?: boolean;
}

/** Not chat models, or not able to drive an agent: embeddings, speech, images, moderation, … */
const NOT_FOR_AGENTS =
  /embed|whisper|tts|speech|audio|transcri|guard|moderation|rerank|imagen|image-|dall-e|sora|veo|lyria|orpheus|playai|aqa|ocr|clip|-vl-|vision-preview|computer-use|realtime|search-preview|translate|stable-diffusion|flux|bge-|-rp-/i;

/**
 * Total parameters in billions from the id: "qwen3-235b-a22b" → 235 (not the active "a22b"); "8x7b" → 56;
 * "command-r7b" → 7.
 */
export function paramsBillions(id: string): number {
  let best = 0;
  for (const m of id.toLowerCase().matchAll(/(?<![a-z])(\d+)x(\d+(?:\.\d+)?)b\b|(?<![a\d.])(\d+(?:\.\d+)?)b\b/g)) {
    const v = m[1] ? Number(m[1]) * Number(m[2]) : Number(m[3]);
    if (v > best) best = v;
  }
  return best;
}

/** How capable a model looks for agent work (only comparable within a rough band). */
export function modelScore(provider: string, m: ModelInfo): number {
  const id = m.id.toLowerCase();
  let s = 0;
  const b = paramsBillions(id);
  if (b) s += Math.min(Math.log2(b) * 8, 80);
  if (/\bpro\b|-pro\b|-pro-/.test(id)) s += 35;
  if (/ultra|large|-max\b|opus/.test(id)) s += 25;
  if (/medium|sonnet/.test(id)) s += 12;
  // "mini" only as its own word: "gemini" is not a mini model.
  if (/flash-lite|\blite\b|-lite|(?<![a-z])mini\b|nano|tiny|small|instant|haiku|lightning/.test(id)) s -= 25;
  else if (/flash/.test(id)) s += 12;
  if (/coder|codestral|devstral|-code\b|qwen.*code/.test(id)) s += 15;
  if (/gpt-oss|kimi-k2|deepseek-(v3|v4|r1|chat)|qwen3|glm-4|glm-5|llama-4|nemotron|grok|mistral-large|magistral|command-a/.test(id)) s += 20;
  if (/llama-3\.3/.test(id)) s += 10;
  const gem = /gemini-(\d+(?:\.\d+)?)/.exec(id);
  if (gem) s += Number(gem[1]) * 10;
  // Newer versions of the same open family first (glm-4.7 over glm-4.5, qwen3.8 over qwen3.5).
  const ver = /(glm-|qwen|llama-|deepseek-v|nemotron-|kimi-k)(\d+(?:\.\d+)?)/.exec(id);
  if (ver) s += Number(ver[2]) * 2;
  if (/preview|-exp\b|experimental|beta/.test(id)) s -= 4;
  if (m.contextWindow) s += Math.min(m.contextWindow / 16_000, 10);
  if (m.tools === true) s += 10;
  if (provider === "gemini" && /gemma/.test(id)) s -= 100; // no tool calling through the Gemini API
  return s;
}

export type ModelClass = "small" | "medium" | "large";

/**
 * Small (fast, cheap on limits, fine for simple work), medium, or large (the strongest, for complex work), from
 * the id: size in parameters and tier words ("mini", "flash-lite", "pro", "ultra").
 */
export function modelClass(m: ModelInfo): ModelClass {
  const id = m.id.toLowerCase();
  const b = paramsBillions(id);
  const strongWord = /\bpro\b|-pro\b|-pro-|ultra|large|-max\b|opus/.test(id);
  if (!strongWord && (/flash-lite|\blite\b|-lite|(?<![a-z])mini\b|nano|tiny|small|instant|haiku|lightning/.test(id) || (b > 0 && b <= 15))) return "small";
  if (b >= 100 || strongWord || /kimi-k2|deepseek-(v3|v4|r1)|qwen3(\.\d+)?-coder|gpt-oss-120b|grok|command-a\b|command-a-/.test(id)) return "large";
  return "medium";
}

/** The provider's models that can drive an agent, best first. */
export function rankModels(provider: string, models: ModelInfo[]): ModelInfo[] {
  const preset = providerPreset(provider);
  const free = preset?.freeModels ? new RegExp(preset.freeModels, "i") : null;
  const paid = preset?.paidModels ? new RegExp(preset.paidModels, "i") : null;
  const usable = models.filter((m) => {
    if (!m.id || NOT_FOR_AGENTS.test(m.id)) return false;
    if (m.tools === false) return false;
    // Only free models where a provider also sells paid ones: a paid one would fail without credit, or spend it.
    if (free && !(m.free === true || free.test(m.id))) return false;
    if (paid?.test(m.id)) return false;
    return true;
  });
  return usable
    .map((m) => ({ m, s: modelScore(provider, m) }))
    .sort((a, b) => b.s - a.s || a.m.id.localeCompare(b.m.id))
    .map((x) => x.m);
}
