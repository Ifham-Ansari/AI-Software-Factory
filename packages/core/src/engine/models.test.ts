import { describe, expect, it } from "vitest";
import { modelClass, rankModels } from "./models.ts";

const ids = (provider: string, list: Parameters<typeof rankModels>[1]) => rankModels(provider, list).map((m) => m.id);

describe("picking a provider's best model", () => {
  it("Groq: the biggest capable chat model, without speech or guard models", () => {
    const ranked = ids(
      "groq",
      ["llama-3.1-8b-instant", "llama-3.3-70b-versatile", "openai/gpt-oss-120b", "openai/gpt-oss-20b", "whisper-large-v3", "meta-llama/llama-guard-4-12b", "playai-tts"].map((id) => ({ id })),
    );
    expect(ranked[0]).toBe("openai/gpt-oss-120b");
    expect(ranked).not.toContain("whisper-large-v3");
    expect(ranked).not.toContain("meta-llama/llama-guard-4-12b");
    expect(ranked).not.toContain("playai-tts");
    expect(ranked.indexOf("llama-3.3-70b-versatile")).toBeLessThan(ranked.indexOf("llama-3.1-8b-instant"));
  });

  it("OpenRouter: free models with tool calling only", () => {
    const ranked = ids("openrouter", [
      { id: "anthropic/claude-opus", tools: true, free: false },
      { id: "meta-llama/llama-3.3-70b-instruct:free", tools: true, free: true, contextWindow: 65_536 },
      { id: "nvidia/nemotron-3-ultra-550b-a55b:free", tools: true, free: true, contextWindow: 131_072 },
      { id: "some/vision-model:free", tools: false, free: true },
    ]);
    expect(ranked).toEqual(["nvidia/nemotron-3-ultra-550b-a55b:free", "meta-llama/llama-3.3-70b-instruct:free"]);
  });

  it("Gemini: newest Flash first, then Flash-Lite; Pro left out (no free quota); no embeddings, images, or Gemma (no tools there)", () => {
    const ranked = ids(
      "gemini",
      ["gemini-3.5-flash", "gemini-3.8-flash", "gemini-3.8-pro", "gemini-3.5-flash-lite", "gemma-4-31b-it", "text-embedding-004", "imagen-4.0-generate"].map((id) => ({ id })),
    );
    expect(ranked.slice(0, 3)).toEqual(["gemini-3.8-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite"]);
    expect(ranked).not.toContain("gemini-3.8-pro");
    expect(ranked).not.toContain("text-embedding-004");
    expect(ranked).not.toContain("imagen-4.0-generate");
    expect(ranked.at(-1)).toBe("gemma-4-31b-it");
  });

  it("follows each provider's free rules: Kilo and OpenRouter :free only, Z.ai Flash only, Cloudflare's paid models out", () => {
    expect(ids("kilo", [{ id: "nvidia/nemotron-3-ultra-550b-a55b:free" }, { id: "anthropic/claude-opus" }])).toEqual(["nvidia/nemotron-3-ultra-550b-a55b:free"]);
    // Z.ai: only GLM-4.x Flash is free; GLM-5.x Flash and the FlashX models need a balance.
    expect(ids("zai", ["glm-5.2", "glm-5.3-flash", "glm-5.3-flashx", "glm-4.7-flashx", "glm-4.7-flash", "glm-4.5-flash"].map((id) => ({ id })))).toEqual(["glm-4.7-flash", "glm-4.5-flash"]);
    expect(ids("cloudflare", [{ id: "@cf/moonshotai/kimi-k2.6" }, { id: "@cf/openai/gpt-oss-120b" }, { id: "@cf/zai-org/glm-5.3" }])).toEqual(["@cf/openai/gpt-oss-120b"]);
  });

  it("sorts models into small, medium, and large", () => {
    const cls = (id: string) => modelClass({ id });
    expect(["llama-3.1-8b-instant", "gemini-3.5-flash-lite", "openai/gpt-oss-20b-mini", "command-r7b", "nvidia/nemotron-3.5-lightning:free", "mistral-small-latest"].map(cls)).toEqual(Array(6).fill("small"));
    expect(["llama-3.3-70b-versatile", "gemini-3.8-flash", "openai/gpt-oss-20b", "glm-4.7-flash", "qwen3.8-27b", "fake-model"].map(cls)).toEqual(Array(6).fill("medium"));
    expect(["openai/gpt-oss-120b", "nvidia/nemotron-3-ultra-550b-a55b:free", "Qwen3.5-397B-A17B", "mistral-large-latest", "moonshotai/kimi-k2-instruct", "command-a-03-2025"].map(cls)).toEqual(Array(6).fill("large"));
  });

  it("reads mixture-of-experts sizes as the total, and prefers coding models", () => {
    expect(ids("custom", [{ id: "qwen3-235b-a22b" }, { id: "llama-3.1-70b" }])[0]).toBe("qwen3-235b-a22b");
    expect(ids("mistral", [{ id: "mistral-small-latest" }, { id: "codestral-latest" }])[0]).toBe("codestral-latest");
    expect(ids("custom", [])).toEqual([]);
  });
});
