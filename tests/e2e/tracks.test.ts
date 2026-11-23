import fs from "node:fs";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, events, startHarness, taskFile, waitFor, type Harness } from "../helpers.ts";

let h: Harness | undefined;
afterEach(async () => {
  await cleanup(h);
  h = undefined;
});

const T1 = taskFile("T001", { role: "frontend", owns: ["src/T001.txt"], title: "Make the header blue" });
const T2 = taskFile("T002", { role: "frontend", owns: ["src/T002.txt"], title: "Rename the button" });

/** Direct-mode engineer run: edit, verify, hand off. */
const build = [
  { asf: ["task", "start", "${ASF_TASK}"] },
  { write: "src/${ASF_TASK}.txt", content: "done ${ASF_TASK}\n" },
  { write: ".asf/handoffs/${ASF_TASK}.md", content: "# Handoff ${ASF_TASK}\n" },
  { asf: ["task", "done", "${ASF_TASK}", "--status", "DONE", "--handoff", ".asf/handoffs/${ASF_TASK}.md"] },
];

const triage = (track: string, files: Record<string, string> = {}) => ({
  steps: [
    ...Object.entries(files).map(([f, c]) => ({ write: `.asf/tasks/${f}`, content: c })),
    ...(Object.keys(files).length ? [{ asf: ["plan", "submit", ".asf/tasks/"] }] : []),
    { write: ".asf/docs/triage.md", content: `track: ${track}\n\nUnderstood the request. Next: ${track}.\n` },
    { asf: ["doc", "submit", "triage"] },
  ],
});

describe("process tracks (fake claude, direct mode)", () => {
  it("quick: triage plans the task, it is built and finished with no PRD, design, review, or QA; the next request works the same way", async () => {
    h = await startHarness(
      {
        "tech-lead:triage": [triage("quick", { "T001.md": T1 }), triage("quick", { "T001.md": T1, "T002.md": T2 })],
        "frontend:implement": { steps: build },
      },
      { workspace: "direct" },
    );
    const svc = h.project.svc;
    fs.writeFileSync(path.join(h.root, "index.html"), "<!doctype html><h1>Sample site</h1>");
    await h.api("POST", "/idea", { text: "Make the header blue" });
    expect(svc.tasks({ kind: ["planning"] })[0]).toMatchObject({ role: "tech-lead", mode: "triage" });
    await waitFor(() => svc.phase === "done", "quick request done", 90_000);

    expect(svc.state.track).toBe("quick");
    expect(fs.readFileSync(path.join(h.root, "src/T001.txt"), "utf8")).toBe("done T001\n");
    // Only the tech lead (triage) and the engineer worked: no PM, designer, reviewer, or QA.
    expect([...new Set(svc.runs({ limit: 50 }).map((r) => r.role))].sort()).toEqual(["frontend", "tech-lead"]);
    expect(svc.doc("prd")).toBeNull();
    expect(svc.task("T001")).toMatchObject({ status: "done" });
    const titles = (await h.api("GET", "/notifications")).map((n: any) => n.data.notify.title);
    expect(titles).toEqual(expect.arrayContaining(["T001 is done", "All done"]));
    expect(titles.some((t: string) => /Process: quick/.test(t))).toBe(true);
    // Nothing was waiting for the owner, so no "Review ..." notifications.
    expect(titles.filter((t: string) => t.startsWith("Review"))).toEqual([]);

    // The finished build is running: a plain HTML project gets a static server.
    const preview = await waitFor(async () => {
      const s = await h!.api("GET", "/preview");
      return s.running && s.url ? s : null;
    }, "preview running", 20_000);
    expect(preview.source).toMatch(/static files/);
    expect(await (await fetch(preview.url)).text()).toContain("Sample site");
    await waitFor(async () => (await h!.api("GET", "/notifications")).some((n: any) => n.data.notify.title === "Your app is running"), "preview notification");
    await h.api("POST", "/preview/stop", {});
    expect((await h.api("GET", "/preview")).running).toBe(false);

    // The next request: straight from "done", same quick flow.
    await h.api("POST", "/idea", { text: "Rename the button" });
    await waitFor(() => svc.task("T002")?.status === "done" && svc.phase === "done", "second request done", 90_000);
    expect(fs.readFileSync(path.join(h.root, "src/T002.txt"), "utf8")).toBe("done T002\n");
  }, 200_000);

  it("standard: triage asks for a short PRD; after approval the plan comes next, without design or architecture", async () => {
    h = await startHarness(
      {
        "tech-lead:triage": triage("standard"),
        "pm:draft": {
          steps: [
            { expectPrompt: "Standard track" },
            { write: ".asf/docs/prd.md", content: "# PRD\n\n- FR-1 export to CSV\n" },
            { asf: ["doc", "submit", "prd"] },
          ],
        },
        "tech-lead:plan": { steps: [{ expectPrompt: "Standard track" }, { text: "planning" }] },
      },
      { workspace: "direct" },
    );
    const svc = h.project.svc;
    await h.api("POST", "/idea", { text: "Export the orders list to CSV" });
    await waitFor(() => svc.phase === "prd_review", "short PRD submitted", 60_000);
    expect(svc.state.track).toBe("standard");
    expect(svc.questions()).toHaveLength(0); // no discovery questions
    const titles = (await h.api("GET", "/notifications")).map((n: any) => n.data.notify.title);
    expect(titles).toContain("Review the PRD");
    await h.api("POST", "/gates/prd/approve", {});
    expect(svc.phase).toBe("plan_review");
    expect(svc.tasks({ kind: ["planning"] }).map((t) => t.mode)).toEqual(["triage", "draft", "plan"]);
    expect(events(h, "task.created").some((e) => e.data.mode === "direction")).toBe(false);
  }, 120_000);

  it("cancelling moves unfinished tasks' files aside; a new plan may not reuse a finished task's id or put app files in .asf/", async () => {
    const T2after = taskFile("T002", { role: "frontend", owns: ["src/T002.txt"], title: "Rename the button", after: ["T001"] });
    h = await startHarness(
      {
        "tech-lead:triage": triage("quick", { "T001.md": T1, "T002.md": T2after }),
        "task:T001:implement": { steps: build },
        "task:T002:implement": { steps: [{ asf: ["task", "start", "${ASF_TASK}"] }, { sleep: 60_000 }] },
      },
      { workspace: "direct" },
    );
    const svc = h.project.svc;
    await h.api("POST", "/idea", { text: "Two small fixes", track: "quick" });
    const running = (id: string) => svc.runs({ active: true }).filter((r) => r.task === id).length;
    await waitFor(() => svc.task("T001")?.status === "done" && running("T002") === 1, "T001 done, T002 running", 90_000);
    await h.api("POST", "/cancel", {});
    const dir = path.join(h.root, ".asf", "tasks");
    expect(fs.readdirSync(dir).filter((f) => f.endsWith(".md"))).toEqual(["T001.md"]);
    expect(fs.existsSync(path.join(dir, "cancelled", "T002.md"))).toBe(true);

    // The next plan: T001 is taken (finished), and app files never go in .asf/; finished tasks' old files are fine.
    const r = await h.project.cmds.planCheck({ kind: "human" }, [
      { file: ".asf/tasks/T001-new.md", source: taskFile("T001", { role: "frontend", owns: ["src/footer.txt"], title: "Footer text" }) },
      { file: ".asf/tasks/T003.md", source: taskFile("T003", { role: "frontend", owns: [".asf/static/index.html"], title: "Hidden page" }) },
    ]);
    expect(r.exit).toBe(1);
    expect(r.text).toMatch(/\[id_taken\] T001 is already the id of "Make the header blue" \(done\).*for example T004/);
    expect(r.text).toMatch(/\[asf_path\] T003: owns "\.asf\/static\/index\.html", inside \.asf\//);
  }, 150_000);

  it("approving a document stops a revision still working on it, without counting it as a failure", async () => {
    h = await startHarness(
      {
        "tech-lead:triage": triage("standard"),
        "pm:draft": { steps: [{ write: ".asf/docs/prd.md", content: "# PRD\n\n- FR-1 export to CSV\n" }, { asf: ["doc", "submit", "prd"] }] },
        // The first plan run submits; the revision after the owner's feedback keeps working until it is stopped.
        "tech-lead:plan": [{ steps: [{ write: ".asf/tasks/T001.md", content: T1 }, { asf: ["plan", "submit", ".asf/tasks/"] }] }, { steps: [{ sleep: 60_000 }] }],
      },
      { workspace: "direct" },
    );
    const svc = h.project.svc;
    await h.api("POST", "/idea", { text: "Export the orders list to CSV" });
    await waitFor(() => svc.phase === "prd_review", "PRD submitted", 60_000);
    await h.api("POST", "/gates/prd/approve", {});
    await waitFor(() => svc.doc("plan")?.status === "submitted", "plan submitted", 60_000);
    const first = svc.tasks({ kind: ["planning"] }).find((t) => t.mode === "plan")!;
    await h.api("POST", "/gates/plan/request-changes", { comment: "Split T001 in two." });
    const running = (id: string) => svc.runs({ active: true }).filter((r) => r.task === id).length;
    const revision = await waitFor(() => svc.tasks({ kind: ["planning"] }).find((t) => t.mode === "plan" && t.id !== first.id && running(t.id) === 1), "revision running", 60_000);
    // The owner changes their mind and approves the plan as submitted: the revision stops.
    await h.api("POST", "/gates/plan/approve", {});
    await waitFor(() => running(revision.id) === 0, "the revision stopped", 30_000);
    expect(svc.task(revision.id)).toMatchObject({ status: "done", hold: "cancelled", run_failures: 0 });
    expect(svc.phase).toBe("build");
    expect(events(h, "alert.raised").filter((e) => e.task === revision.id)).toHaveLength(0);
  }, 150_000);

  it("an agent cannot ask itself; the release follow-up may change the project's files", async () => {
    h = await startHarness(
      { "tech-lead:triage": { steps: [{ asf: ["ask", "@tech-lead", "Should I split this?"], allowFail: true }, ...triage("standard").steps] }, "pm:draft": { steps: [{ sleep: 60_000 }] } },
      { workspace: "direct" },
    );
    const svc = h.project.svc;
    await h.api("POST", "/idea", { text: "Export the orders list to CSV" });
    await waitFor(() => svc.state.track === "standard", "triage done", 60_000);
    // The question was refused (no answer task for itself), and the run went on.
    expect(svc.questions()).toHaveLength(0);
    const triageRun = svc.runs({ limit: 20 }).find((r) => r.agent === "tech-lead-1")!;
    expect(fs.readFileSync(path.join(h.project.paths.runs, triageRun.id, "stream.jsonl"), "utf8")).toMatch(/@tech-lead is you\. Decide it yourself/);

    // (Straight to the release review; the build itself is covered elsewhere.)
    svc.setPhase("release_review");
    await h.project.orch.requestChanges("release", "The menu page is empty.");
    const follow = svc.tasks({ kind: ["integrate"] }).at(-1)!;
    expect(follow).toMatchObject({ title: "Release follow-up from the owner", owns: ["**"] });
    expect(follow.body).toMatch(/Fix exactly what the owner asked, in the project's files/);
  }, 150_000);

  it("the owner can pick a track, and cancel current work to start over", async () => {
    h = await startHarness({ "pm:discover": { steps: [{ sleep: 60_000 }] } }, { workspace: "direct" });
    const svc = h.project.svc;
    await h.api("POST", "/idea", { text: "A big new product", track: "full" });
    expect(svc.tasks({ kind: ["planning"] })[0]).toMatchObject({ role: "pm", mode: "discover" });
    await waitFor(() => svc.runs({ active: true }).length === 1, "PM working");
    // A second request while one is in flight is refused with a clear message.
    await expect(h.api("POST", "/idea", { text: "something else" })).rejects.toThrow(/still working on the current request/);
    await h.api("POST", "/cancel", {});
    expect(svc.phase).toBe("idea");
    expect(svc.runs({ active: true })).toHaveLength(0);
    expect(svc.state.paused).toBe(false);
    expect(svc.tasks().every((t) => t.status === "done")).toBe(true);
    // And a fresh request can be sent right away.
    await h.api("POST", "/idea", { text: "Just change the footer text", track: "quick" });
    expect(svc.tasks({ kind: ["planning"] }).at(-1)).toMatchObject({ mode: "triage" });
  }, 120_000);
});
