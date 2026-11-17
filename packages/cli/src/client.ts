import fs from "node:fs";
import os from "node:os";
import path from "node:path";

// Thin HTTP client to the local AI Software Factory server. Exit codes: 0 ok, 1 refused, 2 invalid args, 3 not allowed, 4 unreachable.

export class CliError extends Error {
  readonly exit: number;
  constructor(message: string, exit: number) {
    super(message);
    this.exit = exit;
  }
}

export interface Conn {
  url: string;
  token: string;
  project: string | null;
  agent: boolean;
}

function asfHome(): string {
  return process.env.ASF_HOME ?? path.join(os.homedir(), ".asf");
}

export function readServerInfo(): { url: string; token: string; pid: number } | null {
  try {
    return JSON.parse(fs.readFileSync(path.join(asfHome(), "server.json"), "utf8"));
  } catch {
    return null;
  }
}

/** Find the AI Software Factory project root containing `dir` (a folder with .asf/config.yaml). */
export function findProjectRoot(dir = process.cwd()): string | null {
  let cur = path.resolve(dir);
  for (;;) {
    if (fs.existsSync(path.join(cur, ".asf", "config.yaml"))) return cur;
    const up = path.dirname(cur);
    if (up === cur) return null;
    cur = up;
  }
}

export async function projectIdFor(root: string): Promise<string> {
  const { createHash } = await import("node:crypto");
  return createHash("sha1").update(path.resolve(root).replace(/\\/g, "/").toLowerCase()).digest("hex").slice(0, 10);
}

export async function connect(opts: { needProject: boolean }): Promise<Conn> {
  if (process.env.ASF_TOKEN && process.env.ASF_SERVER_URL) {
    return { url: process.env.ASF_SERVER_URL, token: process.env.ASF_TOKEN, project: process.env.ASF_PROJECT ?? null, agent: true };
  }
  const info = readServerInfo();
  if (!info) throw new CliError("the AI Software Factory server is not running. Start it with `asf up`.", 4);
  let project: string | null = process.env.ASF_PROJECT ?? null;
  if (!project) {
    const root = findProjectRoot();
    if (root) project = await projectIdFor(root);
  }
  if (opts.needProject && !project) throw new CliError("not inside an AI Software Factory project (no .asf/config.yaml found). Run `asf init` first.", 2);
  return { url: info.url, token: info.token, project, agent: false };
}

export async function request(conn: Conn, method: string, urlPath: string, body?: unknown): Promise<any> {
  const attempt = async () => {
    const res = await fetch(conn.url + urlPath, {
      method,
      headers: { authorization: `Bearer ${conn.token}`, ...(body !== undefined ? { "content-type": "application/json" } : {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    const text = await res.text();
    let json: any;
    try {
      json = text ? JSON.parse(text) : {};
    } catch {
      json = { error: text };
    }
    if (!res.ok) throw new CliError(json.error ?? `HTTP ${res.status}`, Number(json.exit) || (res.status === 401 || res.status === 403 ? 3 : 2));
    return json;
  };
  try {
    return await attempt();
  } catch (e) {
    if (e instanceof CliError) throw e;
    // Unreachable: wait a moment and retry once, as the protocol says.
    await new Promise((r) => setTimeout(r, 2000));
    try {
      return await attempt();
    } catch (e2) {
      if (e2 instanceof CliError) throw e2;
      throw new CliError(`AI Software Factory server unreachable at ${conn.url} (${(e2 as Error).message}). Commit your work and leave your handoff at .asf/handoffs/<task>.md; the orchestrator collects it later.`, 4);
    }
  }
}

export async function cmd(conn: Conn, name: string, body: Record<string, unknown>): Promise<{ ok: boolean; text: string; data: unknown; exit: number }> {
  if (!conn.project) throw new CliError("no project (ASF_PROJECT is not set and the current folder is not an AI Software Factory project)", 2);
  return request(conn, "POST", `/api/projects/${conn.project}/cmd/${name}`, body);
}
