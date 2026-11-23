import { describe, expect, it } from "vitest";
import { alertNote, notificationFor } from "./service.ts";

// What the owner is told: one notification per thing that happened, with a title that says what it was.

describe("owner notifications", () => {
  it("an alert's first sentence is its title", () => {
    expect(alertNote("Usage limit reached. AI Software Factory pauses until 16:05 and then resumes automatically.")).toEqual({
      title: "Usage limit reached",
      body: "AI Software Factory pauses until 16:05 and then resumes automatically.",
    });
    expect(alertNote("Checks failed after T005. Repair task R-001 was created for the tech lead.").title).toBe("Checks failed after T005");
    expect(alertNote("Could not start T001: spawn ENOENT")).toEqual({ title: "Could not start T001: spawn ENOENT" });
    // A dot inside a file name or a number is not the end of a sentence.
    expect(alertNote("T001.md misses owns after 2.5 retries. Fix it.").title).toBe("T001.md misses owns after 2.5 retries");
    expect(alertNote(`${"a very long first sentence ".repeat(6)}.`).title).toBe("AI Software Factory needs your attention");
  });

  it("a blocked task is announced once, not again by its alert", () => {
    expect(notificationFor("task.status", "P-001 ready → blocked", { to: "blocked", reason: "3 runs ended without finishing: run failed" }, { task: "P-001" })).toMatchObject({
      level: "warning",
      title: "P-001 is blocked",
      screen: "board",
      task: "P-001",
    });
    expect(notificationFor("alert.raised", "P-001 is blocked after 3 failed runs: run failed. Check the agent log.", { taskBlocked: true }, { task: "P-001" })).toBeNull();
    expect(notificationFor("alert.raised", "Usage limit reached. Resumes at 16:05.", {}, {})).toMatchObject({ level: "warning", title: "Usage limit reached", body: "Resumes at 16:05.", screen: "questions" });
  });
});
