import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { runTool, type ToolContext } from "./tools.ts";

let dir: string;
let ctx: ToolContext;
beforeEach(() => {
  dir = fs.mkdtempSync(path.join(os.tmpdir(), "asf-tools-"));
  ctx = { cwd: dir, env: process.env as Record<string, string>, signal: new AbortController().signal, runId: "R-test", children: new Set() };
});
afterEach(() => fs.rmSync(dir, { recursive: true, force: true }));

describe("engine tools", () => {
  it("writes, reads with line numbers, and pages long files", async () => {
    expect((await runTool("Write", { file_path: "src/a.txt", content: "one\ntwo\nthree" }, ctx)).ok).toBe(true);
    const r = await runTool("Read", { file_path: "src/a.txt", offset: 2, limit: 1 }, ctx);
    expect(r.output).toMatch(/^\s+2\ttwo/);
    expect(r.output).toMatch(/3 lines in the file; showing 2–2/);
    expect((await runTool("Read", { file_path: "missing.txt" }, ctx)).ok).toBe(false);
  });

  it("edits only an exact, unique match (and handles Windows line endings)", async () => {
    fs.writeFileSync(path.join(dir, "f.ts"), "a = 1;\r\nb = 1;\r\nb = 1;\r\n");
    expect((await runTool("Edit", { file_path: "f.ts", old_string: "a = 1;\nb = 1;", new_string: "a = 2;\nb = 1;" }, ctx)).ok).toBe(true);
    expect(fs.readFileSync(path.join(dir, "f.ts"), "utf8")).toBe("a = 2;\r\nb = 1;\r\nb = 1;\r\n");
    const dup = await runTool("Edit", { file_path: "f.ts", old_string: "b = 1;", new_string: "b = 3;" }, ctx);
    expect(dup).toMatchObject({ ok: false });
    expect(dup.output).toMatch(/occurs 2 times/);
    expect((await runTool("Edit", { file_path: "f.ts", old_string: "b = 1;", new_string: "b = 3;", replace_all: true }, ctx)).ok).toBe(true);
    expect((await runTool("Edit", { file_path: "f.ts", old_string: "nope", new_string: "x" }, ctx)).output).toMatch(/not found/);
  });

  it("runs bash with the exit code and finds files and text", async () => {
    fs.mkdirSync(path.join(dir, "src/deep"), { recursive: true });
    fs.mkdirSync(path.join(dir, "node_modules/x"), { recursive: true });
    fs.writeFileSync(path.join(dir, "src/deep/app.ts"), "export const answer = 42;\n");
    fs.writeFileSync(path.join(dir, "node_modules/x/app.ts"), "export const answer = 42;\n");
    const ok = await runTool("Bash", { command: "echo hello" }, ctx);
    expect(ok).toEqual({ ok: true, output: "hello" });
    const bad = await runTool("Bash", { command: "exit 3" }, ctx);
    expect(bad.ok).toBe(false);
    expect(bad.output).toMatch(/exit code 3/);
    expect((await runTool("Glob", { pattern: "*.ts" }, ctx)).output).toBe("src/deep/app.ts");
    expect((await runTool("Grep", { pattern: "answer\\s*=", output_mode: "content" }, ctx)).output).toBe("src/deep/app.ts:1:export const answer = 42;");
    expect((await runTool("Nope", {}, ctx)).ok).toBe(false);
  });
});
