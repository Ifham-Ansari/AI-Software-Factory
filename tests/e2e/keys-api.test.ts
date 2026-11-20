import fs from "node:fs";
import { afterEach, describe, expect, it } from "vitest";
import { startFakeLlm, type FakeLlm } from "../../packages/fake-claude/src/llm.ts";
import { cleanup, startHarness, type Harness } from "../helpers.ts";

// The owner's API for the team's keys (the Keys screen): keys go in, but never come back out.

let h: Harness | undefined;
let llm: FakeLlm | undefined;
afterEach(async () => {
  await llm?.close();
  llm = undefined;
  await cleanup(h);
  h = undefined;
});

async function call(token: string, method: string, path: string, body?: unknown): Promise<{ status: number; json: any; text: string }> {
  const res = await fetch(`${h!.server.url}${path}`, {
    method,
    headers: { authorization: `Bearer ${token}`, ...(body !== undefined ? { "content-type": "application/json" } : {}) },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  return { status: res.status, json: text ? JSON.parse(text) : null, text };
}

describe("keys API", () => {
  it("adds, tests, lists models for, and removes keys without ever returning one", async () => {
    h = await startHarness({});
    llm = await startFakeLlm({ scenarioFile: process.env.ASF_FAKE_SCENARIO!, stateDir: h.stateDir });
    const owner = h.server.tokens.master;

    const info = await call(owner, "GET", "/api/engine");
    expect(info.status).toBe(200);
    expect(info.json.providers.map((p: { id: string }) => p.id)).toEqual(expect.arrayContaining(["gemini", "groq", "openrouter", "ollama", "custom"]));
    expect(info.json.keys).toEqual([]);

    const good = await call(owner, "POST", "/api/keys", { provider: "custom", label: "Ayesha", key: "sk-secret-good-123456", baseUrl: llm.url });
    expect(good.status).toBe(200);
    expect(good.json).toMatchObject({ label: "Ayesha", masked: "••••3456", invalid: null });
    expect(good.text).not.toContain("sk-secret");
    const bad = await call(owner, "POST", "/api/keys", { provider: "custom", label: "Bilal", key: "bad-secret-999999", baseUrl: llm.url });

    // Testing uses GET /models (no tokens): a rejected key is marked, a working one reports its models.
    expect((await call(owner, "POST", `/api/keys/${good.json.id}/test`, {})).json).toEqual({ ok: true, models: 2 });
    const failed = await call(owner, "POST", `/api/keys/${bad.json.id}/test`, {});
    expect(failed.json).toMatchObject({ ok: false, error: expect.stringMatching(/401/) });

    const listed = await call(owner, "GET", "/api/engine");
    expect(listed.text).not.toContain("secret");
    expect(listed.json.keys.find((k: { id: string }) => k.id === bad.json.id).invalid).toMatch(/401/);

    // Model lists come only from working keys; custom servers are named by their key id.
    const models = await call(owner, "GET", "/api/engine/models");
    expect(models.json).toEqual([{ provider: good.json.id, label: `Ayesha (${llm.url})`, models: ["fake-fast", "fake-model"] }]);

    expect((await call(owner, "POST", "/api/keys", { provider: "custom", label: "X", key: "k", baseUrl: "ftp://nope" })).status).toBe(400);
    expect((await call(owner, "POST", "/api/keys", { provider: "nope", label: "X", key: "k" })).status).toBe(400);

    expect((await call(owner, "DELETE", `/api/keys/${bad.json.id}`)).status).toBe(200);
    expect((await call(owner, "DELETE", `/api/keys/${bad.json.id}`)).status).toBe(404);
    expect(fs.readFileSync(h.keys!.file, "utf8")).not.toContain("bad-secret");
  });

  it("agents cannot see or change the team's keys", async () => {
    h = await startHarness({});
    h.keys!.add({ provider: "groq", label: "Ayesha", key: "gsk-secret-123456" });
    const agent = h.server.tokens.issue(h.project.id, { kind: "agent", agent: "backend-1", role: "backend", task: "T001", runId: "R-00001" });
    for (const [method, path, body] of [
      ["GET", "/api/engine", undefined],
      ["GET", "/api/engine/models", undefined],
      ["POST", "/api/keys", { provider: "groq", label: "x", key: "y" }],
      ["DELETE", `/api/keys/${h.keys!.list()[0]!.id}`, undefined],
    ] as const) {
      const r = await call(agent, method, path, body);
      expect(r.status, `${method} ${path}`).toBe(403);
      expect(r.text).not.toContain("gsk-secret");
    }
    expect(h.keys!.list()).toHaveLength(1);
  });
});
