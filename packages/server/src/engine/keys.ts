import { maskKey, providerPreset, type PoolKey, type PoolKeyState } from "@asf/core";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { asfHome } from "../paths.ts";

// The team's API keys for the built-in engine. They live on the host computer in ~/.asf/keys.json (never in a
// project folder), are readable only by the server, and never reach agent processes: the guard blocks the files,
// agents' environments get no key, and only the HTTP client puts a key in an Authorization header.

export interface StoredKey extends PoolKey {
  key: string;
  /** Required for custom and local providers; otherwise the provider preset's URL. */
  baseUrl?: string;
  addedAt: string;
}

export interface KeyView {
  id: string;
  provider: string;
  label: string;
  masked: string;
  baseUrl: string;
  addedAt: string;
  invalid: string | null;
  cooldownUntil: number | null;
  usageToday: { requests: number; input: number; output: number };
}

type UsageFile = Record<string, Record<string, { requests: number; input: number; output: number }>>;

function writePrivate(file: string, data: unknown): void {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const tmp = `${file}.${process.pid}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(data, null, 2), { mode: 0o600 });
  fs.renameSync(tmp, file);
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export class KeyStore {
  readonly file: string;
  readonly usageFile: string;
  /** Rate-limit cooldowns and last use, in memory (a restart forgets them, which is safe). */
  readonly state: Record<string, PoolKeyState> = {};
  private cache: { mtime: number; keys: StoredKey[] } | null = null;

  constructor(dir = asfHome()) {
    this.file = path.join(dir, "keys.json");
    this.usageFile = path.join(dir, "key-usage.json");
  }

  /** Read on every call (cached by mtime), so `asf keys add` takes effect while the server runs. */
  list(): StoredKey[] {
    let mtime = 0;
    try {
      mtime = fs.statSync(this.file).mtimeMs;
    } catch {
      return [];
    }
    if (this.cache?.mtime === mtime) return this.cache.keys;
    try {
      const j = JSON.parse(fs.readFileSync(this.file, "utf8")) as { keys?: StoredKey[] };
      this.cache = { mtime, keys: Array.isArray(j.keys) ? j.keys : [] };
    } catch {
      this.cache = { mtime, keys: [] };
    }
    return this.cache.keys;
  }

  private save(keys: StoredKey[]): void {
    writePrivate(this.file, { keys });
    this.cache = null;
  }

  get(id: string): StoredKey | undefined {
    return this.list().find((k) => k.id === id);
  }

  add(input: { provider: string; label: string; key: string; baseUrl?: string }): StoredKey {
    const preset = providerPreset(input.provider);
    if (!preset && input.provider !== "custom") throw new Error(`Unknown provider "${input.provider}".`);
    const baseUrl = (input.baseUrl ?? "").trim() || undefined;
    if (input.provider === "custom" && !baseUrl) throw new Error("A custom provider needs its base URL (ending in /v1 for most).");
    if (!preset?.keyless && !input.key.trim()) throw new Error("The key is empty.");
    const k: StoredKey = {
      id: `k_${crypto.randomBytes(4).toString("hex")}`,
      provider: input.provider,
      label: input.label.trim() || "unnamed",
      key: input.key.trim(),
      baseUrl,
      addedAt: new Date().toISOString(),
      invalid: null,
    };
    this.save([...this.list(), k]);
    return k;
  }

  remove(id: string): boolean {
    const keys = this.list();
    const next = keys.filter((k) => k.id !== id);
    if (next.length === keys.length) return false;
    this.save(next);
    delete this.state[id];
    return true;
  }

  setInvalid(id: string, reason: string | null): void {
    this.save(this.list().map((k) => (k.id === id ? { ...k, invalid: reason } : k)));
  }

  cooldown(id: string, until: number): void {
    this.state[id] = { ...this.state[id], cooldownUntil: until };
  }

  touch(id: string): void {
    this.state[id] = { ...this.state[id], lastUsed: Date.now() };
  }

  baseUrl(k: StoredKey): string {
    return k.baseUrl || providerPreset(k.provider)?.baseUrl || "";
  }

  recordUsage(id: string, input: number, output: number): void {
    let u: UsageFile = {};
    try {
      u = JSON.parse(fs.readFileSync(this.usageFile, "utf8")) as UsageFile;
    } catch {
      /* first use */
    }
    const d = today();
    // Keep a week of history.
    for (const day of Object.keys(u)) if (day < new Date(Date.now() - 7 * 86_400_000).toISOString().slice(0, 10)) delete u[day];
    const row = (u[d] ??= {})[id] ?? { requests: 0, input: 0, output: 0 };
    u[d]![id] = { requests: row.requests + 1, input: row.input + input, output: row.output + output };
    try {
      writePrivate(this.usageFile, u);
    } catch {
      /* usage numbers are informational */
    }
  }

  usageToday(): Record<string, { requests: number; input: number; output: number }> {
    try {
      return (JSON.parse(fs.readFileSync(this.usageFile, "utf8")) as UsageFile)[today()] ?? {};
    } catch {
      return {};
    }
  }

  /** Safe to show: never the key itself. */
  views(): KeyView[] {
    const usage = this.usageToday();
    const now = Date.now();
    return this.list().map((k) => ({
      id: k.id,
      provider: k.provider,
      label: k.label,
      masked: k.key ? maskKey(k.key) : "(no key)",
      baseUrl: this.baseUrl(k),
      addedAt: k.addedAt,
      invalid: k.invalid ?? null,
      cooldownUntil: (this.state[k.id]?.cooldownUntil ?? 0) > now ? this.state[k.id]!.cooldownUntil! : null,
      usageToday: usage[k.id] ?? { requests: 0, input: 0, output: 0 },
    }));
  }
}

const stores = new Map<string, KeyStore>();

/** One store per key file, shared by every project the server has open (their runs share the team's limits). */
export function sharedKeyStore(dir = asfHome()): KeyStore {
  let s = stores.get(dir);
  if (!s) {
    s = new KeyStore(dir);
    stores.set(dir, s);
  }
  return s;
}
