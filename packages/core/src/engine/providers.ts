// OpenAI-compatible providers the built-in engine knows. Model lists are read live from each provider's
// GET /models, so no model id is hard-coded here (free models change often).

export interface ProviderPreset {
  id: string;
  label: string;
  baseUrl: string;
  /** Where to create a key. */
  keyUrl?: string;
  /** Local servers need no key. */
  keyless?: boolean;
  /** One line for the owner: what the free tier is like. */
  note: string;
}

export const PROVIDERS: ProviderPreset[] = [
  { id: "gemini", label: "Google Gemini", baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai", keyUrl: "https://aistudio.google.com/apikey", note: "Free tier with daily limits; Google may use free-tier prompts to improve its models." },
  { id: "groq", label: "Groq", baseUrl: "https://api.groq.com/openai/v1", keyUrl: "https://console.groq.com/keys", note: "Free tier, very fast, small per-minute token limits." },
  { id: "openrouter", label: "OpenRouter", baseUrl: "https://openrouter.ai/api/v1", keyUrl: "https://openrouter.ai/keys", note: "Many models; those ending in :free cost nothing but have daily request limits." },
  { id: "mistral", label: "Mistral", baseUrl: "https://api.mistral.ai/v1", keyUrl: "https://console.mistral.ai/api-keys", note: "Free experiment tier with rate limits." },
  { id: "cerebras", label: "Cerebras", baseUrl: "https://api.cerebras.ai/v1", keyUrl: "https://cloud.cerebras.ai", note: "Free tier with daily token limits." },
  { id: "ollama", label: "Ollama (this computer)", baseUrl: "http://127.0.0.1:11434/v1", keyless: true, note: "Free and unlimited; runs models on your own computer (needs a strong GPU)." },
  { id: "lmstudio", label: "LM Studio (this computer)", baseUrl: "http://127.0.0.1:1234/v1", keyless: true, note: "Free and unlimited; runs models on your own computer (needs a strong GPU)." },
  { id: "custom", label: "Other (OpenAI-compatible)", baseUrl: "", note: "Any service with an OpenAI-compatible /chat/completions endpoint." },
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
