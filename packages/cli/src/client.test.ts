import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { findProjectRoot, projectRootForUp } from "./client.ts";

// Which project a folder belongs to: agents run in subfolders of a project; `asf up` in a new folder starts one.

let dir: string;
afterEach(() => fs.rmSync(dir, { recursive: true, force: true }));

describe("finding the project", () => {
  it("asf up in a new, empty folder inside another project's folder sets up a new project", () => {
    dir = fs.mkdtempSync(path.join(os.tmpdir(), "asf-root-"));
    // A folder of projects that was itself set up as a project.
    fs.mkdirSync(path.join(dir, ".asf"));
    fs.writeFileSync(path.join(dir, ".asf", "config.yaml"), "existing: false\n");
    const fresh = path.join(dir, "bakery-site");
    const code = path.join(dir, "src", "app");
    fs.mkdirSync(fresh);
    fs.mkdirSync(code, { recursive: true });
    fs.writeFileSync(path.join(code, "main.ts"), "");
    expect(projectRootForUp(fresh)).toBeNull();
    // A folder with files in it is part of the project, as before; agents' commands always look upwards.
    expect(projectRootForUp(code)).toBe(dir);
    expect(findProjectRoot(fresh)).toBe(dir);
    expect(projectRootForUp(dir)).toBe(dir);
  });
});
