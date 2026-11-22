import path from "node:path";
import { describe, expect, it } from "vitest";
import { buildSystemPrompt, focusMode } from "./prompts.ts";

// A run's instructions carry only its own mode of each skill: every request of a run resends them.

const SKILLS = path.resolve(import.meta.dirname, "../../../skills");

describe("instructions for one mode", () => {
  const skill = [
    "# Tech Lead",
    "",
    "Intro for every mode.",
    "",
    "## Mode: triage",
    "Size the request.",
    "",
    "## Mode: plan",
    "Write task files like this:",
    "```markdown",
    "## Goal",
    "```",
    "",
    "## Mode: architect (with contracts)",
    "Write the architecture.",
    "",
    "## Principles",
    "Shared by all modes.",
  ].join("\n");

  it("keeps the run's mode and the shared sections, and names the modes it left out", () => {
    const out = focusMode(skill, "plan", "skills/tech-lead/SKILL.md");
    expect(out).toContain("Intro for every mode.");
    expect(out).toContain("## Mode: plan");
    // A heading inside a code block is part of the mode, not a section of its own.
    expect(out).toContain("```markdown\n## Goal\n```");
    expect(out).toContain("## Principles\nShared by all modes.");
    expect(out).not.toContain("Size the request.");
    expect(out).not.toContain("Write the architecture.");
    expect(out).toContain("The other modes (triage, architect) are left out here; they are in `skills/tech-lead/SKILL.md`.");
  });

  it("keeps a skill whole when it has no section for the mode", () => {
    expect(focusMode(skill, "ruling", "x")).toBe(skill);
    expect(focusMode(skill, undefined, "x")).toBe(skill);
  });

  it("with the real skills: a plan run gets the plan mode only; an engineer's skills are unchanged", () => {
    const base = { roleTitle: "Tech Lead", project: "demo", skills: ["team-protocol", "tech-lead", "engineering-discipline"], skillsDir: SKILLS };
    const all = buildSystemPrompt(base);
    const plan = buildSystemPrompt({ ...base, mode: "plan" });
    expect(plan).toContain("## Mode: plan");
    expect(plan).not.toContain("## Mode: architect");
    expect(plan).toContain("# AI Software Factory Team Protocol");
    expect(plan.length).toBeLessThan(all.length * 0.85);
    const backend = { ...base, roleTitle: "Backend Engineer", skills: ["team-protocol", "engineering-discipline", "backend-engineer"] };
    expect(buildSystemPrompt({ ...backend, mode: "implement" })).toBe(buildSystemPrompt(backend));
    // The short instructions point at the run's section instead.
    expect(buildSystemPrompt({ ...base, mode: "plan", lean: true })).toContain("(this run: its `## Mode: plan` section)");
  });
});
