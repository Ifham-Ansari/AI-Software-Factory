import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { ModelCatalog } from "./catalog.ts";
import { KeyStore } from "./keys.ts";

// The model catalog: live model lists, the presets' fallback lists, and the automatic choice by task level.

let dir: string;
let server: http.Server;
let url: string;
let models: unknown[] | null;

beforeEach(async () => {
  dir = fs.mkdtempSync(path.join(os.tmpdir(), "asf-catalog-"));
  models = null;
  server = http.createServer((req, res) => {
    // A provider that lists its models, or (models = null) one without a model list.
    if (models && req.url?.endsWith("/models")) {
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ data: models }));
    } else {
      res.writeHead(404, { "content-type": "application/json" });
      res.end('{"error":{"message":"not found"}}');
    }
  });
  await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
  url = `http://127.0.0.1:${(server.address() as { port: number }).port}/v1`;
});
afterEach(async () => {
  await new Promise<void>((r) => server.close(() => r()));
  fs.rmSync(dir, { recursive: true, force: true });
});

describe("model catalog", () => {
  it("uses the preset's known models when a provider does not list its own", async () => {
    const keys = new KeyStore(dir);
    keys.add({ provider: "zai", label: "Ayesha", key: "zai-key-123456", baseUrl: url });
    const catalog = new ModelCatalog(keys);
    await catalog.refresh();
    expect(catalog.list()).toEqual([{ provider: "zai", label: "Z.ai (GLM)", models: ["glm-4.7-flash", "glm-4.5-flash"], best: "glm-4.7-flash" }]);
  });

  it("routes by task level across every key's models", async () => {
    models = [{ id: "big-model-120b" }, { id: "mid-model-70b" }, { id: "tiny-model-8b" }, { id: "text-embedding-3" }];
    const keys = new KeyStore(dir);
    const k = keys.add({ provider: "custom", label: "Ayesha", key: "custom-key-123456", baseUrl: url });
    const catalog = new ModelCatalog(keys);
    await catalog.refresh();
    const ref = (m: string) => `${k.id}:${m}`;
    expect(catalog.routes()).toEqual({
      light: [ref("tiny-model-8b"), ref("mid-model-70b"), ref("big-model-120b")],
      // Small models only do light work while bigger ones exist.
      standard: [ref("mid-model-70b"), ref("big-model-120b")],
      heavy: [ref("big-model-120b"), ref("mid-model-70b")],
    });
    expect(catalog.autoRefs("light")[0]).toBe(ref("tiny-model-8b"));
    // A model that cannot work is left out from then on.
    catalog.markBad(ref("tiny-model-8b"));
    expect(catalog.autoRefs("light")[0]).toBe(ref("mid-model-70b"));
  });

  it("reports a provider that cannot be reached and has no known models", async () => {
    const keys = new KeyStore(dir);
    keys.add({ provider: "custom", label: "Bilal", key: "custom-key-654321", baseUrl: url });
    const catalog = new ModelCatalog(keys);
    await catalog.refresh();
    expect(catalog.list()[0]).toMatchObject({ models: [], best: null, error: expect.stringMatching(/404/) });
    expect(catalog.routes()).toEqual({ light: [], standard: [], heavy: [] });
  });
});
