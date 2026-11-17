import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

/** Root of the AI Software Factory installation (the cloned repo). */
export const ASF_REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");

export const CLI_ENTRY = path.join(ASF_REPO, "packages/cli/src/main.ts");
export const DASHBOARD_DIST = path.join(ASF_REPO, "packages/dashboard/dist");
export const SKILLS_SOURCE = path.join(ASF_REPO, "skills");
export const ROLES_SOURCE = path.join(ASF_REPO, "roles.yaml");

/**
 * Identifies the AI Software Factory code on disk: the newest modification time of the server, core, and CLI sources. A running
 * server compares it with the CLI's to notice it is older than the code (after `git pull`) and should restart.
 */
export function buildId(): string {
  let newest = 0;
  const walk = (dir: string) => {
    let entries: fs.Dirent[];
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const e of entries) {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) walk(p);
      else if (e.name.endsWith(".ts")) newest = Math.max(newest, fs.statSync(p).mtimeMs);
    }
  };
  for (const pkg of ["core", "server", "cli"]) walk(path.join(ASF_REPO, "packages", pkg, "src"));
  return String(Math.floor(newest));
}

/** Per-user AI Software Factory state (registry of projects, server info). Never inside ~/.claude. */
export function asfHome(): string {
  const h = process.env.ASF_HOME ?? path.join(os.homedir(), ".asf");
  fs.mkdirSync(h, { recursive: true });
  return h;
}

/** Node flags for every AI Software Factory-owned Node process. */
export const NODE_FLAGS = ["--disable-warning=ExperimentalWarning"];

/** Command line that runs the asf CLI (used for hooks and agent PATH shims). */
export function cliCommand(): string[] {
  return [process.execPath, ...NODE_FLAGS, CLI_ENTRY];
}

export function quoteArg(a: string): string {
  return /^[A-Za-z0-9_\-./:=@]+$/.test(a) ? a : `"${a.replace(/(["\\$`])/g, "\\$1")}"`;
}

export class ProjectPaths {
  readonly root: string;
  constructor(root: string) {
    this.root = root;
  }
  get name(): string {
    return path.basename(this.root);
  }
  get asf(): string {
    return path.join(this.root, ".asf");
  }
  get db(): string {
    return path.join(this.asf, "asf.db");
  }
  get config(): string {
    return path.join(this.asf, "config.yaml");
  }
  get runs(): string {
    return path.join(this.asf, "runs");
  }
  get attachments(): string {
    return path.join(this.asf, "attachments");
  }
  get bin(): string {
    return path.join(this.asf, "bin");
  }
  /** Worktrees live next to the project: <parent>/.asf-worktrees/<project>/<name>. */
  get worktrees(): string {
    return path.join(path.dirname(this.root), ".asf-worktrees", this.name);
  }
  get integration(): string {
    return path.join(this.worktrees, "_integration");
  }
  run(id: string): string {
    return path.join(this.runs, id);
  }
}
