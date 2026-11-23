import { describe, expect, it } from "vitest";
import { PROVIDERS } from "./providers.ts";
import { pickKey, type PoolKey } from "./pool.ts";
import { routeModels, taskLevel, type RoutableModel } from "./routing.ts";

describe("how demanding a run is", () => {
  const level = (mode: string, extra: Partial<Parameters<typeof taskLevel>[0]> = {}) => taskLevel({ mode, stage: "implement", ...extra });

  it("by mode: answers are light, sizing and discovery are standard, product, design, architecture, and plans are heavy", () => {
    expect(level("answer")).toBe("light");
    // Sizing a request writes the tasks itself on the quick track.
    expect(["triage", "discover", "survey"].map((m) => level(m))).toEqual(["standard", "standard", "standard"]);
    expect(["draft", "screens", "architect", "plan", "integrate", "scaffold", "release"].map((m) => level(m))).toEqual(Array(7).fill("heavy"));
  });

  it("by task size for building and reviewing", () => {
    expect(["S", "M", "L"].map((size) => level("implement", { size }))).toEqual(["light", "standard", "heavy"]);
    // Reviews need judgment whatever the size.
    expect(["S", "M", "L"].map((size) => level("review", { size, stage: "review" }))).toEqual(["standard", "standard", "standard"]);
    expect(level("implement", { size: null })).toBe("standard");
  });

  it("moves up after a failure, and a fix after review is never left to the smallest", () => {
    expect(level("implement", { size: "S", failures: 1 })).toBe("standard");
    expect(level("implement", { size: "S", failures: 5 })).toBe("heavy");
    expect(level("answer", { failures: 1 })).toBe("standard");
    expect(level("fix", { size: "S", stage: "fix" })).toBe("standard");
  });

  it("does not leave work for real users to the smallest models", () => {
    expect(level("implement", { size: "S", stakes: "customer-facing" })).toBe("standard");
    expect(level("implement", { size: "S", stakes: "hobby" })).toBe("light");
    // Answering a teammate stays light whatever the stakes.
    expect(level("answer", { stakes: "regulated" })).toBe("light");
  });
});

describe("routing models to a level", () => {
  const m = (ref: string, cls: RoutableModel["class"], score: number): RoutableModel => ({ ref, class: cls, score });
  const all = [
    m("groq:openai/gpt-oss-120b", "large", 80),
    m("groq:llama-3.3-70b-versatile", "medium", 60),
    m("groq:llama-3.1-8b-instant", "small", 20),
    m("gemini:gemini-3.8-flash", "medium", 70),
    m("gemini:gemini-3.5-flash-lite", "small", 30),
    m("nvidia:nvidia/nemotron-3-ultra-550b-a55b", "large", 95),
  ];

  it("light work starts with small models, complex work with the largest, each with the rest as backups", () => {
    expect(routeModels("light", all)).toEqual([
      "gemini:gemini-3.5-flash-lite",
      "groq:llama-3.1-8b-instant",
      "gemini:gemini-3.8-flash",
      "groq:llama-3.3-70b-versatile",
      "nvidia:nvidia/nemotron-3-ultra-550b-a55b",
      "groq:openai/gpt-oss-120b",
    ]);
    expect(routeModels("heavy", all).slice(0, 2)).toEqual(["nvidia:nvidia/nemotron-3-ultra-550b-a55b", "groq:openai/gpt-oss-120b"]);
    expect(routeModels("standard", all)[0]).toBe("gemini:gemini-3.8-flash");
  });

  it("standard and complex work wait for bigger models instead of falling back to small ones", () => {
    expect(routeModels("heavy", all)).toEqual(["nvidia:nvidia/nemotron-3-ultra-550b-a55b", "groq:openai/gpt-oss-120b", "gemini:gemini-3.8-flash", "groq:llama-3.3-70b-versatile"]);
    expect(routeModels("standard", all)).toEqual(["gemini:gemini-3.8-flash", "groq:llama-3.3-70b-versatile", "nvidia:nvidia/nemotron-3-ultra-550b-a55b", "groq:openai/gpt-oss-120b"]);
    // With only small models there is nothing better to wait for, so they do everything.
    const small = all.filter((x) => x.class === "small");
    expect(routeModels("heavy", small)).toEqual(["gemini:gemini-3.5-flash-lite", "groq:llama-3.1-8b-instant"]);
  });

  it("keeps a few models per provider and size, and the list short", () => {
    const many = Array.from({ length: 6 }, (_, i) => m(`groq:small-${i}-8b`, "small", 50 - i));
    expect(routeModels("light", many)).toEqual(["groq:small-0-8b", "groq:small-1-8b"]);
    expect(routeModels("light", all, 2, 3)).toHaveLength(3);
  });
});

describe("per-model limits", () => {
  const keys: PoolKey[] = [{ id: "a", provider: "groq", label: "Ayesha" }];
  const NOW = 1_900_000_000_000;

  it("a model at its limit leaves the key's other models usable", () => {
    const state = { a: { models: { "openai/gpt-oss-120b": NOW + 60_000 } } };
    expect(pickKey(["groq:openai/gpt-oss-120b", "groq:llama-3.1-8b-instant"], keys, state, NOW)).toMatchObject({ ok: true, model: "llama-3.1-8b-instant" });
    expect(pickKey(["groq:openai/gpt-oss-120b"], keys, state, NOW)).toMatchObject({ ok: false, reason: "limited", resetsAt: NOW + 60_000 });
  });

  it("a limit for the whole key stops all its models", () => {
    expect(pickKey(["groq:a", "groq:b"], keys, { a: { cooldownUntil: NOW + 5000 } }, NOW)).toMatchObject({ ok: false, reason: "limited", resetsAt: NOW + 5000 });
  });
});

describe("provider presets", () => {
  it("are complete, and say whether each is free, a trial, or local", () => {
    for (const p of PROVIDERS) {
      expect(p.note.length, p.id).toBeGreaterThan(20);
      if (p.id === "custom") continue;
      expect(p.baseUrl, p.id).toMatch(p.tier === "local" ? /^http:\/\/127\.0\.0\.1:\d+\/v1$/ : /^https:\/\//);
      if (!p.keyless) expect(p.keyUrl, p.id).toMatch(/^https:\/\//);
    }
    expect(new Set(PROVIDERS.map((p) => p.id)).size).toBe(PROVIDERS.length);
    // GitHub Models was retired in July 2026; Cerebras is trial credit only.
    expect(PROVIDERS.find((p) => p.id === "github")).toBeUndefined();
    expect(PROVIDERS.find((p) => p.id === "cerebras")?.tier).toBe("trial");
  });
});
