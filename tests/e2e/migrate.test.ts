import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { AsfServer, git, initProject } from "@asf/server";

let dir: string | undefined;
afterEach(() => {
  if (dir) fs.rmSync(dir, { recursive: true, force: true, maxRetries: 3 });
  dir = undefined;
});

describe("old worktree projects move to the owner's folder", () => {
  it("merges finished and unfinished work into the folder, removes worktrees, and switches to direct mode", async () => {
    dir = fs.mkdtempSync(path.join(os.tmpdir(), "asf-migrate-"));
    process.env.ASF_HOME = path.join(dir, "home");
    const root = path.join(dir, "site");
    fs.mkdirSync(root);
    fs.writeFileSync(path.join(root, "index.html"), "<h1>site</h1>");
    // An isolated project, as older AI Software Factory versions made them.
    const init = await initProject(root, { workspace: "isolated" });
    const integ = init.integration;
    fs.writeFileSync(path.join(integ, "about.html"), "<h1>about</h1>");
    await git(integ, ["add", "-A"]);
    await git(integ, ["commit", "-q", "-m", "finished work"]);
    // An unfinished task on its own branch and worktree.
    const wt = path.join(path.dirname(integ), "frontend-1-T002");
    await git(root, ["worktree", "add", "-q", "-b", "asf/T002-contact", wt, "asf/integration"]);
    fs.writeFileSync(path.join(wt, "contact.html"), "<h1>contact (in progress)</h1>");
    await git(wt, ["add", "-A"]);
    await git(wt, ["commit", "-q", "-m", "T002 work so far"]);

    let server = new AsfServer({ port: 0, writeInfo: false, autoStart: false });
    await server.start();
    let p = await server.openProject(root);
    expect(p.direct).toBe(false);
    p.svc.createTask({ id: "T002", kind: "build", title: "Contact page", role: "frontend", status: "in_progress", owns: ["contact.html"], verify: "true" });
    p.svc.updateTask("T002", { worktree: wt, branch: "asf/T002-contact", session_id: "old-session" });
    await server.stop();

    // Pre-direct projects have no `workspace` line in their config.
    const cfg = path.join(root, ".asf", "config.yaml");
    fs.writeFileSync(cfg, fs.readFileSync(cfg, "utf8").replace(/^workspace:.*\n/m, ""));

    server = new AsfServer({ port: 0, writeInfo: false, autoStart: false });
    await server.start();
    p = await server.openProject(root);
    try {
      expect(p.direct).toBe(true);
      // Finished and unfinished work are in the owner's folder now.
      expect(fs.readFileSync(path.join(root, "about.html"), "utf8")).toBe("<h1>about</h1>");
      expect(fs.readFileSync(path.join(root, "contact.html"), "utf8")).toContain("in progress");
      // No worktrees left.
      expect(fs.existsSync(path.dirname(integ))).toBe(false);
      expect((await git(root, ["worktree", "list"])).stdout.trim().split("\n")).toHaveLength(1);
      // The task continues in the folder, fresh session, and its diff shows its own work.
      expect(p.svc.task("T002")).toMatchObject({ worktree: null, branch: null, session_id: null, status: "in_progress" });
      expect(p.orch.taskDiff(p.svc.task("T002")!).files).toEqual([{ path: "contact.html", status: "added" }]);
      expect(fs.readFileSync(cfg, "utf8")).toMatch(/^workspace: direct$/m);
      expect(p.svc.events({ types: ["project.moved"] })).toHaveLength(1);
    } finally {
      await server.stop();
    }
  }, 60_000);
});
