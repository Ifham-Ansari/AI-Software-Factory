import { TOOL_CAPS } from "@asf/core";
import { spawn } from "node:child_process";
import { execa } from "execa";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import picomatch from "picomatch";
import { killTree } from "../runner.ts";
import { findShell } from "../shell.ts";

// What the built-in engine's tools do. The guard has already approved the call before any of these run.

export interface ToolContext {
  cwd: string;
  env: Record<string, string>;
  signal: AbortSignal;
  runId: string;
  /** Pids of commands still running (foreground or background), killed when the run ends. */
  children: Set<number>;
}

export interface ToolOutcome {
  ok: boolean;
  output: string;
}

const ok = (output: string): ToolOutcome => ({ ok: true, output });
const fail = (output: string): ToolOutcome => ({ ok: false, output });

const SKIP_DIRS = new Set(["node_modules", ".git", ".venv", "venv", "__pycache__", ".next", ".turbo", ".pytest_cache", ".mypy_cache", "dist", "build"]);
const SKIP_ASF = new Set(["runs", "sessions", "snapshots", "asf.db", "asf.db-wal", "asf.db-shm"]);

function rel(cwd: string, abs: string): string {
  const r = path.relative(cwd, abs);
  return (r && !r.startsWith("..") && !path.isAbsolute(r) ? r : abs).replace(/\\/g, "/");
}

function tail(s: string, n: number): string {
  return s.length > n ? `…(${s.length - n} earlier characters cut)\n${s.slice(-n)}` : s;
}

function* walk(dir: string): Generator<string> {
  let entries: fs.Dirent[];
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return;
  }
  for (const e of entries) {
    const full = path.join(dir, e.name);
    if (e.isDirectory()) {
      if (SKIP_DIRS.has(e.name)) continue;
      if (path.basename(dir) === ".asf" && SKIP_ASF.has(e.name)) continue;
      yield* walk(full);
    } else if (e.isFile()) {
      if (path.basename(dir) === ".asf" && SKIP_ASF.has(e.name)) continue;
      yield full;
    }
  }
}

function readText(abs: string): string | null {
  const st = fs.statSync(abs);
  if (st.size > 2_000_000) return null;
  const buf = fs.readFileSync(abs);
  if (buf.subarray(0, 8000).includes(0)) return null;
  return buf.toString("utf8");
}

function toolRead(input: Record<string, any>, ctx: ToolContext): ToolOutcome {
  const raw = String(input.file_path ?? "");
  if (!raw) return fail("Read needs file_path.");
  const abs = path.resolve(ctx.cwd, raw);
  if (!fs.existsSync(abs)) return fail(`File does not exist: ${raw}`);
  if (fs.statSync(abs).isDirectory()) return fail(`${raw} is a folder. Use Glob or Bash (ls) to list it.`);
  const text = readText(abs);
  if (text === null) return fail(`${raw} is binary or larger than 2 MB.`);
  if (!text) return ok("(empty file)");
  const lines = text.split(/\r?\n/);
  const from = Math.max(1, Number(input.offset) || 1);
  const limit = Math.max(1, Math.min(Number(input.limit) || TOOL_CAPS.readLines, TOOL_CAPS.readLines));
  const shown = lines.slice(from - 1, from - 1 + limit);
  let out = shown.map((l, i) => `${String(from + i).padStart(6)}\t${l}`).join("\n");
  if (out.length > TOOL_CAPS.readChars) out = `${out.slice(0, TOOL_CAPS.readChars)}\n…(cut; use offset and limit)`;
  const last = from - 1 + shown.length;
  if (from > 1 || last < lines.length) out += `\n(${lines.length} lines in the file; showing ${from}–${last}. Use offset to read more.)`;
  return ok(out);
}

function toolWrite(input: Record<string, any>, ctx: ToolContext): ToolOutcome {
  const raw = String(input.file_path ?? "");
  if (!raw) return fail("Write needs file_path.");
  const abs = path.resolve(ctx.cwd, raw);
  fs.mkdirSync(path.dirname(abs), { recursive: true });
  const content = String(input.content ?? "");
  fs.writeFileSync(abs, content);
  return ok(`Wrote ${rel(ctx.cwd, abs)} (${content.split("\n").length} lines).`);
}

function countOf(hay: string, needle: string): number {
  let n = 0;
  for (let i = hay.indexOf(needle); i >= 0; i = hay.indexOf(needle, i + needle.length)) n++;
  return n;
}

function toolEdit(input: Record<string, any>, ctx: ToolContext): ToolOutcome {
  const raw = String(input.file_path ?? "");
  const abs = path.resolve(ctx.cwd, raw);
  if (!raw || !fs.existsSync(abs)) return fail(`File does not exist: ${raw}. Use Write to create it.`);
  let oldS = String(input.old_string ?? "");
  let newS = String(input.new_string ?? "");
  if (!oldS) return fail("old_string is empty. Use Write to create or replace a whole file.");
  if (oldS === newS) return fail("old_string and new_string are the same; nothing to change.");
  const text = fs.readFileSync(abs, "utf8");
  let n = countOf(text, oldS);
  // The model usually sends \n; Windows files may use \r\n.
  if (n === 0 && text.includes("\r\n") && !oldS.includes("\r\n")) {
    const o2 = oldS.replace(/\n/g, "\r\n");
    const c2 = countOf(text, o2);
    if (c2) {
      oldS = o2;
      newS = newS.replace(/\n/g, "\r\n");
      n = c2;
    }
  }
  if (n === 0) return fail(`old_string was not found in ${raw}. Read the file and copy the text exactly, including indentation.`);
  if (n > 1 && !input.replace_all) return fail(`old_string occurs ${n} times in ${raw}. Include more surrounding lines to make it unique, or set replace_all.`);
  const next = input.replace_all ? text.split(oldS).join(newS) : text.replace(oldS, () => newS);
  fs.writeFileSync(abs, next);
  return ok(`Edited ${rel(ctx.cwd, abs)} (${input.replace_all ? n : 1} replacement${n > 1 && input.replace_all ? "s" : ""}).`);
}

async function toolBash(input: Record<string, any>, ctx: ToolContext): Promise<ToolOutcome> {
  const command = String(input.command ?? "").trim();
  if (!command) return fail("Bash needs a command.");
  if (input.run_in_background) {
    const dir = path.join(os.tmpdir(), "asf-bg");
    fs.mkdirSync(dir, { recursive: true });
    const log = path.join(dir, `${ctx.runId}-${Date.now()}.log`);
    const fd = fs.openSync(log, "a");
    const child = spawn(findShell(), ["-c", command], {
      cwd: ctx.cwd,
      env: ctx.env,
      detached: process.platform !== "win32",
      stdio: ["ignore", fd, fd],
      windowsHide: true,
    });
    fs.closeSync(fd);
    child.on("error", () => {});
    child.unref();
    if (child.pid) ctx.children.add(child.pid);
    return ok(`Started in the background (pid ${child.pid ?? "?"}). Its output goes to ${log.replace(/\\/g, "/")}; read it with Bash (tail).`);
  }
  const seconds = Math.min(Math.max(Number(input.timeout) || TOOL_CAPS.bashTimeoutSeconds, 1), TOOL_CAPS.bashMaxTimeoutSeconds);
  const sub = execa(findShell(), ["-c", command], {
    cwd: ctx.cwd,
    env: ctx.env,
    extendEnv: false,
    stdin: "ignore",
    reject: false,
    all: true,
    stripFinalNewline: true,
    windowsHide: true,
  });
  const pid = sub.pid;
  if (pid) ctx.children.add(pid);
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    if (pid) void killTree(pid);
  }, seconds * 1000);
  const onAbort = () => {
    if (pid) void killTree(pid);
  };
  ctx.signal.addEventListener("abort", onAbort, { once: true });
  const r = await sub;
  clearTimeout(timer);
  ctx.signal.removeEventListener("abort", onAbort);
  if (pid) ctx.children.delete(pid);
  const output = tail(String(r.all ?? ""), TOOL_CAPS.bashChars);
  if (timedOut) return fail(`${output}\n(stopped after ${seconds} s; for a server or watcher, use run_in_background)`);
  const code = r.exitCode ?? 1;
  return code === 0 ? ok(output || "(no output)") : fail(`${output}\n(exit code ${code})`);
}

function baseDir(input: Record<string, any>, ctx: ToolContext): string {
  return path.resolve(ctx.cwd, String(input.path ?? "."));
}

function toolGrep(input: Record<string, any>, ctx: ToolContext): ToolOutcome {
  let re: RegExp;
  try {
    re = new RegExp(String(input.pattern ?? ""), input["-i"] ? "i" : "");
  } catch (e) {
    return fail(`Invalid regular expression: ${(e as Error).message}`);
  }
  const base = baseDir(input, ctx);
  if (!fs.existsSync(base)) return fail(`No such file or folder: ${input.path}`);
  const glob = input.glob ? picomatch(String(input.glob), { dot: true, basename: !String(input.glob).includes("/") }) : null;
  const mode = String(input.output_mode ?? "files_with_matches");
  const files = fs.statSync(base).isFile() ? [base] : [...walk(base)];
  const out: string[] = [];
  for (const f of files) {
    if (out.length >= TOOL_CAPS.listResults) break;
    const r = rel(ctx.cwd, f);
    if (glob && !glob(path.relative(base, f).replace(/\\/g, "/"))) continue;
    let text: string | null;
    try {
      text = readText(f);
    } catch {
      continue;
    }
    if (text === null) continue;
    if (mode === "files_with_matches") {
      if (re.test(text)) out.push(r);
      continue;
    }
    const lines = text.split(/\r?\n/);
    let count = 0;
    lines.forEach((l, i) => {
      if (!re.test(l)) return;
      count++;
      if (mode === "content" && out.length < TOOL_CAPS.listResults) out.push(`${r}:${i + 1}:${l.length > 300 ? `${l.slice(0, 300)}…` : l}`);
    });
    if (mode === "count" && count) out.push(`${r}:${count}`);
  }
  if (!out.length) return ok("No matches.");
  return ok(out.join("\n") + (out.length >= TOOL_CAPS.listResults ? `\n(first ${TOOL_CAPS.listResults} results; narrow the search)` : ""));
}

function toolGlob(input: Record<string, any>, ctx: ToolContext): ToolOutcome {
  const base = baseDir(input, ctx);
  if (!fs.existsSync(base)) return fail(`No such folder: ${input.path}`);
  const pattern = String(input.pattern ?? "");
  const isMatch = picomatch(pattern, { dot: true, basename: !pattern.includes("/") });
  const found: { f: string; m: number }[] = [];
  for (const f of walk(base)) {
    if (!isMatch(path.relative(base, f).replace(/\\/g, "/"))) continue;
    let m = 0;
    try {
      m = fs.statSync(f).mtimeMs;
    } catch {
      /* gone */
    }
    found.push({ f, m });
    if (found.length >= 5000) break;
  }
  if (!found.length) return ok("No files found.");
  found.sort((a, b) => b.m - a.m);
  const shown = found.slice(0, TOOL_CAPS.listResults).map((x) => rel(ctx.cwd, x.f));
  return ok(shown.join("\n") + (found.length > shown.length ? `\n(${found.length} files; showing the newest ${shown.length})` : ""));
}

export async function runTool(name: string, input: Record<string, any>, ctx: ToolContext): Promise<ToolOutcome> {
  try {
    switch (name) {
      case "Read":
        return toolRead(input, ctx);
      case "Write":
        return toolWrite(input, ctx);
      case "Edit":
        return toolEdit(input, ctx);
      case "Bash":
        return await toolBash(input, ctx);
      case "Grep":
        return toolGrep(input, ctx);
      case "Glob":
        return toolGlob(input, ctx);
      case "TodoWrite":
        return ok("Todos updated.");
      default:
        return fail(`Unknown tool ${name}. Available: Read, Write, Edit, Bash, Grep, Glob, TodoWrite.`);
    }
  } catch (e) {
    return fail(`${name} failed: ${(e as Error).message}`);
  }
}
