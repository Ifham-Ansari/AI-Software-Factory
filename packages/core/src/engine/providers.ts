// OpenAI-compatible providers the built-in engine knows. Model lists are read live from each provider's
// GET /models where it has one, so model ids are only hard-coded as a fallback (free models change often).
// Researched in November 2026: free tiers, limits, and terms change; each note says what to check.

export interface ProviderPreset {
  id: string;
  label: string;
  baseUrl: string;
  /** Where to create a key. */
  keyUrl?: string;
  /** No key at all (a model on this computer). */
  keyless?: boolean;
  /** Works without a key at a low limit; a free key raises it. */
  keyOptional?: boolean;
  /** The base URL holds the owner's own part (e.g. an account id): the form asks for it. */
  needsBaseUrl?: boolean;
  /** "free": an ongoing free tier; "trial": one-time credit; "local": runs on this computer. */
  tier: "free" | "trial" | "local";
  /** Whether a rate limit is per model (switch to another model of the same key) or for the whole account. */
  limitScope: "model" | "key";
  /** The model list, when it is not `${baseUrl}/models`. */
  modelsUrl?: string;
  /** Used when the provider does not list its models (or listing fails). */
  defaultModels?: string[];
  /** Only ids matching this (a regular expression) are free; the others would cost money or have no free quota. */
  freeModels?: string;
  /** Ids matching this are not free on this provider, so they are never picked automatically. */
  paidModels?: string;
  /** One line for the owner: what the free tier is like, and its catch. */
  note: string;
}

export const PROVIDERS: ProviderPreset[] = [
  {
    id: "gemini",
    label: "Google Gemini",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
    keyUrl: "https://aistudio.google.com/apikey",
    tier: "free",
    limitScope: "model",
    paidModels: "-pro|argon|image|imagen|veo|tts|live",
    note: "Free Flash, Flash-Lite, and Gemma models with daily limits per model (Pro models are paid). Outside the EEA, UK, and Switzerland, Google may use free-tier prompts to improve its products.",
  },
  {
    id: "groq",
    label: "Groq",
    baseUrl: "https://api.groq.com/openai/v1",
    keyUrl: "https://console.groq.com/keys",
    tier: "free",
    limitScope: "model",
    note: "Free and very fast. Limits are per model (for example 1,000 requests and 200k tokens a day, 8k tokens a minute on the biggest), so a second model doubles what you get.",
  },
  {
    id: "openrouter",
    label: "OpenRouter",
    baseUrl: "https://openrouter.ai/api/v1",
    keyUrl: "https://openrouter.ai/keys",
    tier: "free",
    limitScope: "key",
    freeModels: ":free$",
    note: "Many models; those ending in :free cost nothing: 20 a minute and 50 a day for the whole account (1,000 a day after a one-time $10 top-up). Free providers may log prompts.",
  },
  {
    id: "nvidia",
    label: "NVIDIA API Catalog",
    baseUrl: "https://integrate.api.nvidia.com/v1",
    keyUrl: "https://build.nvidia.com",
    tier: "free",
    limitScope: "key",
    defaultModels: ["nvidia/nemotron-3-ultra-550b-a55b", "openai/gpt-oss-120b", "openai/gpt-oss-20b"],
    note: "Free with the NVIDIA Developer Program, about 40 requests a minute, large models (Nemotron Ultra 550B). For prototyping and development, not production; use is logged.",
  },
  {
    id: "mistral",
    label: "Mistral",
    baseUrl: "https://api.mistral.ai/v1",
    keyUrl: "https://console.mistral.ai/api-keys",
    tier: "free",
    limitScope: "model",
    note: "Free Experiment plan (phone verification, no card): about 1 request a second per model. Experiment-plan requests may be used to train Mistral's models.",
  },
  {
    id: "zai",
    label: "Z.ai (GLM)",
    baseUrl: "https://api.z.ai/api/paas/v4",
    keyUrl: "https://z.ai/manage-apikey/apikey-list",
    tier: "free",
    limitScope: "model",
    // Only the GLM-4.x Flash models are free; GLM-5.x Flash and the FlashX models need a balance.
    freeModels: "^glm-4(\\.\\d+)?v?-flash$",
    defaultModels: ["glm-4.7-flash", "glm-4.5-flash"],
    note: "The GLM-4.x Flash models are free with tool calling, one request at a time per model. Newer GLM models (5.x, FlashX) are paid.",
  },
  {
    id: "cloudflare",
    label: "Cloudflare Workers AI",
    baseUrl: "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1",
    keyUrl: "https://dash.cloudflare.com/profile/api-tokens",
    needsBaseUrl: true,
    tier: "free",
    limitScope: "key",
    paidModels: "kimi|glm-5|deepseek-v4",
    defaultModels: ["@cf/openai/gpt-oss-120b", "@cf/meta/llama-3.3-70b-instruct-fp8-fast", "@cf/zai-org/glm-4.7-flash", "@cf/meta/llama-4-scout-17b-16e-instruct"],
    note: "10,000 free Neurons a day for the whole account (resets 00:00 UTC). Put your account id in the base URL; the token needs Workers AI access.",
  },
  {
    id: "sambanova",
    label: "SambaNova Cloud",
    baseUrl: "https://api.sambanova.ai/v1",
    keyUrl: "https://cloud.sambanova.ai/apis",
    tier: "free",
    limitScope: "model",
    defaultModels: ["DeepSeek-V3-0324", "Meta-Llama-3.3-70B-Instruct"],
    note: "Free tier without a card, small per-model limits (about 20 requests a minute and a day each). Check the current limits in your account.",
  },
  {
    id: "ollama-cloud",
    label: "Ollama Cloud",
    baseUrl: "https://ollama.com/v1",
    keyUrl: "https://ollama.com/settings/keys",
    tier: "free",
    limitScope: "key",
    defaultModels: ["gpt-oss:120b", "gpt-oss:20b"],
    note: "Free plan for light use: one model at a time, limits per 5-hour session and per week (not published).",
  },
  {
    id: "kilo",
    label: "Kilo Gateway",
    baseUrl: "https://api.kilo.ai/api/gateway",
    keyUrl: "https://app.kilo.ai",
    tier: "free",
    limitScope: "key",
    freeModels: ":free$|/free$",
    note: "Free models (ids ending in :free), about 200 requests an hour. Its free router may send prompts to providers that log them.",
  },
  {
    id: "ovh",
    label: "OVHcloud AI Endpoints (no key)",
    baseUrl: "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1",
    keyless: true,
    tier: "free",
    limitScope: "model",
    defaultModels: ["gpt-oss-120b", "Qwen3.5-397B-A17B", "Meta-Llama-3_3-70B-Instruct", "gpt-oss-20b"],
    note: "Anonymous use without signup, hosted in the EU: 2 requests a minute per model and per IP. Slow, but a free backup.",
  },
  {
    id: "llm7",
    label: "LLM7.io",
    baseUrl: "https://api.llm7.io/v1",
    keyUrl: "https://token.llm7.io",
    keyOptional: true,
    tier: "free",
    limitScope: "key",
    defaultModels: ["gpt-oss:20b", "codestral-latest"],
    note: "Works without a key at a low limit; a free token gives 60 requests a minute and 100k tokens a day. The free quota may change without notice.",
  },
  {
    id: "axforge",
    label: "AxForge",
    baseUrl: "https://api.axforge.ai/v1",
    keyUrl: "https://axforge.ai",
    tier: "free",
    limitScope: "key",
    defaultModels: ["qwen3.8-27b", "glm-5.3-flash"],
    note: "3M free tokens every 30 days for the whole account, no card. Hosted in Stockholm; says prompts are not stored or used for training.",
  },
  {
    id: "cohere",
    label: "Cohere (trial key)",
    baseUrl: "https://api.cohere.ai/compatibility/v1",
    keyUrl: "https://dashboard.cohere.com/api-keys",
    tier: "free",
    limitScope: "key",
    modelsUrl: "https://api.cohere.com/v1/models?endpoint=chat",
    defaultModels: ["command-a-03-2025"],
    note: "Free trial key: about 1,000 calls a month and 20 a minute, for non-commercial use only.",
  },
  {
    id: "cerebras",
    label: "Cerebras (trial credit)",
    baseUrl: "https://api.cerebras.ai/v1",
    keyUrl: "https://cloud.cerebras.ai",
    tier: "trial",
    limitScope: "model",
    note: "No ongoing free tier since mid-2026: a one-time trial credit after adding a payment method. Very fast while it lasts.",
  },
  {
    id: "ollama",
    label: "Ollama (this computer)",
    baseUrl: "http://127.0.0.1:11434/v1",
    keyless: true,
    tier: "local",
    limitScope: "model",
    note: "Free and unlimited; runs models on your own computer (needs a strong GPU). Nothing leaves your computer.",
  },
  {
    id: "lmstudio",
    label: "LM Studio (this computer)",
    baseUrl: "http://127.0.0.1:1234/v1",
    keyless: true,
    tier: "local",
    limitScope: "model",
    note: "Free and unlimited; runs models on your own computer (needs a strong GPU). Nothing leaves your computer.",
  },
  { id: "custom", label: "Other (OpenAI-compatible)", baseUrl: "", tier: "free", limitScope: "key", note: "Any service with an OpenAI-compatible /chat/completions endpoint." },
];

export function providerPreset(id: string): ProviderPreset | undefined {
  return PROVIDERS.find((p) => p.id === id);
}

/** "groq:llama-3.3-70b-versatile" → provider + model. Model ids may contain colons ("…:free", "qwen2.5-coder:32b"). */
export function parseModelRef(ref: string): { provider: string; model: string } | null {
  const i = ref.indexOf(":");
  if (i <= 0 || i === ref.length - 1) return null;
  return { provider: ref.slice(0, i).trim(), model: ref.slice(i + 1).trim() };
}

/** Show a key without revealing it. */
export function maskKey(key: string): string {
  return key.length <= 8 ? "••••" : `••••${key.slice(-4)}`;
}
