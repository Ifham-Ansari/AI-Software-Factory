import path from "node:path";
import { describe, expect, it } from "vitest";
import { SKILLS_SOURCE } from "../paths.ts";
import { buildSystemPrompt } from "../prompts.ts";
import { engineChain } from "./runner.ts";

const settings = (strong: string[], fast: string[]) => ({ engine_models: { strong, fast }, engine_context_tokens: 32_000 });

describe("which models a run tries", () => {
  it("uses its own list first and the other list as a backup", () => {
    const s = settings(["openrouter:big:free"], ["groq:small"]);
    expect(engineChain({ tier: "fast" }, s)).toEqual(["groq:small", "openrouter:big:free"]);
    expect(engineChain({ tier: "strong" }, s)).toEqual(["openrouter:big:free", "groq:small"]);
    expect(engineChain({ tier: "fast" }, settings(["a:x"], []))).toEqual(["a:x"]);
  });

  it("puts a per-role provider model first, and ignores Claude aliases", () => {
    const s = settings(["a:x"], ["b:y"]);
    expect(engineChain({ tier: "strong", model: "c:z" }, s)).toEqual(["c:z", "a:x", "b:y"]);
    expect(engineChain({ tier: "fast", model: "sonnet" }, s)).toEqual(["b:y", "a:x"]);
    expect(engineChain({ tier: "strong", model: "a:x" }, s)).toEqual(["a:x", "b:y"]);
  });
});

describe("short instructions for small models", () => {
  it("lists the skills by path with their descriptions instead of including them", () => {
    const input = { roleTitle: "Tech Lead", project: "app", skills: ["team-protocol", "tech-lead"], skillsDir: SKILLS_SOURCE, direct: true };
    const full = buildSystemPrompt(input);
    const lean = buildSystemPrompt({ ...input, lean: true });
    const dir = SKILLS_SOURCE.replace(/\\/g, "/");
    expect(lean).toContain(`\`${dir}/team-protocol/SKILL.md\``);
    expect(lean).toContain(`\`${path.posix.join(dir, "tech-lead")}/SKILL.md\`: Use for the AI Software Factory tech lead agent`);
    expect(lean).toMatch(/Before anything else, Read the first file/);
    // The same header (rules, direct-mode note), a fraction of the size.
    expect(lean).toContain("Build only what the owner asked for");
    expect(lean.length).toBeLessThan(full.length / 5);
  });
});
