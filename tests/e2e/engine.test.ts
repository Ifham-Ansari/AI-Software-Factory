import fs from "node:fs";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, DEFAULT_BUILD_SCENARIO, events, implementSteps, seedBuild, startHarness, taskFile, waitFor, type Harness } from "../helpers.ts";

// The built-in engine (free API keys instead of Claude Code), against fake-llm: a scripted OpenAI-compatible
// server acting out the same scenarios as fake-claude, as tool calls the engine really runs.

let h: Harness | undefined;
afterEach(async () => {
  await cleanup(h);
  h = undefined;
});

const done = (id: string) => () => h!.project.svc.task(id)?.status === "done";
const streamOf = (runId: string) => fs.readFileSync(path.join(h!.project.paths.runs, runId, "stream.jsonl"), "utf8");

describe("built-in engine (fake llm)", () => {
  it("builds, reviews, and QAs a task through the engine's own tools", async () => {
    h = await startHarness(DEFAULT_BUILD_SCENARIO, { runner: "engine", workspace: "direct" });
    await seedBuild(h, { "T001.md": taskFile("T001", { role: "backend" }) });
    await waitFor(done("T001"), "T001 done");
    // QA marks the task done before its own run has finished.
    await waitFor(() => h!.project.svc.runs({ task: "T001" }).every((r) => r.ended_at), "runs ended");
    expect(fs.readFileSync(path.join(h.root, "src/T001.txt"), "utf8").replace(/\r\n/g, "\n")).toBe("work of T001\n");
    const runs = h.project.svc.runs({ task: "T001" });
    expect(runs.map((r) => r.stage).sort()).toEqual(["implement", "review", "verify"]);
    expect(runs.every((r) => r.result_status === "success")).toBe(true);
    // The run log is Claude-compatible stream-json, so the dashboard transcript works unchanged.
    const impl = runs.find((r) => r.stage === "implement")!;
    const stream = streamOf(impl.id);
    expect(stream).toMatch(/"type":"tool_use","id":"[^"]+","name":"Write"/);
    expect(stream).toMatch(/"type":"result"/);
    expect(impl.input_tokens).toBeGreaterThan(0);
    // Usage is counted per key, for the team's view of whose quota went where.
    const usage = Object.values(h.keys!.usageToday());
    expect(usage[0]!.requests).toBeGreaterThan(3);
    // The conversation is kept for resuming.
    expect(fs.existsSync(path.join(h.project.paths.asf, "sessions", `${impl.session_id}.json`))).toBe(true);
  });

  it("the guard runs inside the engine: writes outside owns and force pushes are blocked", async () => {
    h = await startHarness(
      {
        ...DEFAULT_BUILD_SCENARIO,
        "backend:implement": {
          steps: [{ asf: ["task", "start", "${ASF_TASK}"] }, { write: "frontend/src/app/page.tsx", content: "not mine" }, { bash: "git push --force origin HEAD", allowFail: true }, ...implementSteps().slice(2)],
        },
      },
      { runner: "engine" },
    );
    await seedBuild(h, { "T001.md": taskFile("T001", { role: "backend" }) });
    await waitFor(done("T001"), "T001 done");
    const blocks = events(h, "guard.blocked").map((b) => b.summary).join("\n");
    expect(blocks).toMatch(/frontend\/src\/app\/page\.tsx is not in this task's owned paths/);
    expect(blocks).toMatch(/git push --force/);
    expect(fs.existsSync(path.join(h.project.paths.integration, "frontend/src/app/page.tsx"))).toBe(false);
    expect(events(h, "run.blocked").length).toBeGreaterThanOrEqual(2);
  });

  it("a rate-limited key hands over to a teammate's key without pausing", async () => {
    h = await startHarness(DEFAULT_BUILD_SCENARIO, { runner: "engine", workspace: "direct", keys: ["limited-key", "good-key"] });
    await seedBuild(h, { "T001.md": taskFile("T001", { role: "backend" }) });
    await waitFor(done("T001"), "T001 done");
    expect(h.project.svc.state.paused).toBe(false);
    const [limited, good] = h.keys!.list();
    expect(h.keys!.state[limited!.id]?.cooldownUntil).toBeGreaterThan(Date.now());
    expect(h.keys!.usageToday()[good!.id]?.requests).toBeGreaterThan(0);
    expect(events(h, "run.retry").some((e) => /Teammate 1's key/.test(e.summary))).toBe(true);
  });

  it("when every key is rate limited, the team pauses until the reset and then resumes", async () => {
    h = await startHarness(
      {
        ...DEFAULT_BUILD_SCENARIO,
        "backend:implement": [{ steps: [{ asf: ["task", "start", "${ASF_TASK}"] }, { usageLimit: { inSeconds: 2 } }] }, { steps: implementSteps() }],
        "backend:implement:resume": { steps: [{ expectPrompt: "usage limit" }, ...implementSteps()] },
      },
      { runner: "engine", workspace: "direct" },
    );
    await seedBuild(h, { "T001.md": taskFile("T001", { role: "backend" }) });
    const limit = await waitFor(() => events(h!, "quota.limit")[0], "usage limit");
    expect(limit.data.resetsAt as number).toBeGreaterThan(Date.now() - 1000);
    await waitFor(() => events(h!, "quota.resumed").length > 0, "auto resume", 20_000);
    await waitFor(done("T001"), "T001 done after the reset");
    const be = h.invocations().filter((i) => i.task === "T001" && i.role === "backend");
    expect(be[1].resume).toBe(true);
    expect(h.project.svc.task("T001")!.run_failures).toBe(0);
  });

  it("with no working key the team pauses with a clear message, and Resume after adding a key continues", async () => {
    h = await startHarness(DEFAULT_BUILD_SCENARIO, { runner: "engine", workspace: "direct", keys: ["bad-key"] });
    await seedBuild(h, { "T001.md": taskFile("T001", { role: "backend" }) });
    await waitFor(() => h!.project.svc.state.paused, "paused");
    expect(h.project.svc.state.pauseReason).toBe("No working API key");
    expect(h.project.svc.state.alerts?.at(-1)?.text).toMatch(/Open Keys to add or fix a key/);
    const t = h.project.svc.task("T001")!;
    expect(t.status).not.toBe("blocked");
    expect(t.run_failures).toBe(0);
    expect(h.keys!.list()[0]!.invalid).toMatch(/401/);
    // The owner adds a working key and clicks Resume.
    h.keys!.add({ provider: "custom", label: "Teammate 2", key: "good-key", baseUrl: h.fakeLlm!.url });
    h.project.orch.resume();
    await waitFor(done("T001"), "T001 done after a key was added");
  });

  it("ask @human: the answer resumes the same engine conversation", async () => {
    h = await startHarness(
      {
        ...DEFAULT_BUILD_SCENARIO,
        "backend:implement": { steps: [{ asf: ["task", "start", "${ASF_TASK}"] }, { asf: ["ask", "@human", "Use the test key for payments?"] }] },
        "backend:implement:resume": { steps: [{ expectPrompt: "Yes, use the test key" }, ...implementSteps()] },
      },
      { runner: "engine", workspace: "direct" },
    );
    await seedBuild(h, { "T001.md": taskFile("T001", { role: "backend" }) });
    const q = await waitFor(() => h!.project.svc.questions("open")[0], "question");
    await waitFor(() => h!.project.svc.runs({ task: "T001" })[0]?.ended_at, "first run ended");
    await h.api("POST", `/questions/${q.id}/answer`, { answer: "Yes, use the test key" });
    await waitFor(done("T001"), "T001 done");
    const impl = h.project.svc.runs({ task: "T001" }).filter((r) => r.stage === "implement");
    expect(impl.map((r) => r.mode).sort()).toEqual(["fresh", "resume"]);
    // The resumed run continued the first conversation: the question is still in its history.
    const resumed = impl.find((r) => r.mode === "resume")!;
    const session = JSON.parse(fs.readFileSync(path.join(h.project.paths.asf, "sessions", `${resumed.session_id}.json`), "utf8"));
    expect(JSON.stringify(session.messages)).toMatch(/Use the test key for payments/);
  });

  it("a weaker model: its own tool names still work, and a reply without tools gets one nudge", async () => {
    h = await startHarness(
      {
        ...DEFAULT_BUILD_SCENARIO,
        "backend:implement": {
          steps: [
            { say: "I will create the file for ${ASF_TASK} now." },
            { asf: ["task", "start", "${ASF_TASK}"] },
            { call: { name: "write_file", input: { path: "src/${ASF_TASK}.txt", text: "work of ${ASF_TASK}\n" } } },
            { call: { name: "read_file", input: { path: "src/${ASF_TASK}.txt" } } },
            ...implementSteps().slice(3),
          ],
        },
      },
      { runner: "engine", workspace: "direct" },
    );
    await seedBuild(h, { "T001.md": taskFile("T001", { role: "backend" }) });
    await waitFor(done("T001"), "T001 done");
    expect(fs.readFileSync(path.join(h.root, "src/T001.txt"), "utf8").replace(/\r\n/g, "\n")).toBe("work of T001\n");
    const impl = h.project.svc.runs({ task: "T001" }).find((r) => r.stage === "implement")!;
    const stream = streamOf(impl.id);
    // The feed and transcript see the real tool names, with ids every provider accepts.
    expect(stream).toMatch(/"type":"tool_use","id":"c\d{5}x\d{2}","name":"Write","input":\{"file_path":"src\/T001.txt"/);
    expect(stream).toMatch(/"name":"Read"/);
    expect(stream).not.toMatch(/"name":"write_file"/);
    const session = JSON.parse(fs.readFileSync(path.join(h.project.paths.asf, "sessions", `${impl.session_id}.json`), "utf8"));
    expect(session.messages.filter((m: { content?: string }) => /replied without calling a tool/.test(m.content ?? ""))).toHaveLength(1);
  });

  it("the kill switch stops engine runs at once and the tasks keep their place", async () => {
    h = await startHarness(
      { ...DEFAULT_BUILD_SCENARIO, "backend:implement": { steps: [{ asf: ["task", "start", "${ASF_TASK}"] }, { hang: true }] } },
      { runner: "engine", workspace: "direct", settings: { max_concurrent_agents: 3 } },
    );
    await seedBuild(h, { "T001.md": taskFile("T001", { role: "backend" }), "T002.md": taskFile("T002", { role: "backend" }) });
    await waitFor(() => h!.project.svc.tasks({ status: "in_progress" }).length === 2, "two agents working");
    const t0 = Date.now();
    const r = await h.api("POST", "/control/kill", {});
    expect(r.killed).toBe(2);
    await waitFor(() => h!.project.svc.runs({ active: true }).length === 0, "runs ended", 3000, 50);
    expect(Date.now() - t0).toBeLessThan(3000);
    expect(h.project.svc.state).toMatchObject({ paused: true, pauseReason: "kill switch" });
    for (const id of ["T001", "T002"]) {
      expect(h.project.svc.task(id)!.status).toBe("in_progress");
      expect(h.project.svc.runs({ task: id })[0]!.result_status).toBe("killed");
    }
  });
});
