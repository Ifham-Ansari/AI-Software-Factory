import { modelClass, modelScore, providerPreset, rankModels, routeModels, type ModelInfo, type RoutableModel, type TaskLevel } from "@asf/core";
import { listModels } from "./client.ts";
import type { KeyStore, StoredKey } from "./keys.ts";

// The models each provider with a working key offers, best first, and the automatic choice for a run: small
// models for light work, the strongest for complex work, from every working key (see routeModels in core). A key
// that was just added is used without touching Settings, and when one provider's or model's limit runs out the
// others take over. Lists come from GET /models (no tokens used), cached for a few hours; providers that do not
// list their models fall back to the preset's known ones.

const FRESH_MS = 6 * 3_600_000;

export interface ProviderModels {
  /** What goes before the colon in a model reference: a provider id, or a custom server's key id. */
  provider: string;
  label: string;
  /** Usable for agents, best first. */
  models: string[];
  best: string | null;
  error?: string;
}

export type ModelRoutes = Record<TaskLevel, string[]>;

interface Entry {
  at: number;
  /** The preset whose rules apply (groq, gemini, …; "custom" for a custom server). */
  preset: string;
  ranked: ModelInfo[];
  error?: string;
}

export class ModelCatalog {
  private readonly keys: KeyStore;
  private readonly cache = new Map<string, Entry>();
  /** Model references that failed for good (no tool calling, unknown id): left out of the automatic picks. */
  private readonly bad = new Set<string>();
  private refreshing: Promise<void> | null = null;

  constructor(keys: KeyStore) {
    this.keys = keys;
  }

  /** One group per provider (keys of one provider share a model list); custom servers each on their own. */
  private groups(): { provider: string; label: string; key: StoredKey }[] {
    const out = new Map<string, { provider: string; label: string; key: StoredKey }>();
    for (const k of this.keys.list().filter((x) => !x.invalid)) {
      const id = k.provider === "custom" ? k.id : k.provider;
      if (!out.has(id)) out.set(id, { provider: id, label: k.provider === "custom" ? `${k.label} (${this.keys.baseUrl(k)})` : (providerPreset(k.provider)?.label ?? k.provider), key: k });
    }
    return [...out.values()];
  }

  /** Fetch the lists that are missing or old (all of them with force). Concurrent callers share one refresh. */
  refresh(force = false): Promise<void> {
    if (this.refreshing) return this.refreshing;
    const due = this.groups().filter((g) => {
      const e = this.cache.get(g.provider);
      return force || !e || Date.now() - e.at > FRESH_MS || (e.error && Date.now() - e.at > 60_000);
    });
    if (!due.length) return Promise.resolve();
    this.refreshing = Promise.all(
      due.map(async (g) => {
        const presetId = g.key.provider;
        const preset = providerPreset(presetId);
        const r = await listModels(this.keys.baseUrl(g.key), g.key.key, 15_000, preset?.modelsUrl);
        // A rejected key is an error; a provider without a model list falls back to its known models.
        const fallback = (preset?.defaultModels ?? []).map((id) => ({ id }));
        const listed = r.ok ? r.models : [];
        let ranked = rankModels(presetId, listed.length ? listed : fallback);
        // Some providers list only their newest models (Z.ai lists its paid GLM-5 models, not the free GLM-4 Flash
        // ones): when nothing listed is usable, use the models known to work. A wrong one is dropped on first use.
        if (!ranked.length && listed.length) ranked = rankModels(presetId, fallback);
        const error = !r.ok && (r.error.kind === "auth" || !fallback.length) ? r.error.message : undefined;
        this.cache.set(g.provider, { at: Date.now(), preset: presetId, ranked, ...(error ? { error } : {}) });
      }),
    ).then(() => {
      this.refreshing = null;
    });
    return this.refreshing;
  }

  markBad(ref: string): void {
    this.bad.add(ref);
  }

  /** Every usable model of every working key, with its size class and score. */
  routable(): RoutableModel[] {
    return this.groups().flatMap((g) => {
      const e = this.cache.get(g.provider);
      if (!e) return [];
      return e.ranked
        .map((m) => ({ ref: `${g.provider}:${m.id}`, class: modelClass(m), score: modelScore(e.preset, m) }))
        .filter((m) => !this.bad.has(m.ref));
    });
  }

  /**
   * The automatic models for a run of this level, in order (small first for light work, the strongest first for
   * complex work). Without a level: each provider's best model, in the order the keys were added.
   */
  autoRefs(level?: TaskLevel): string[] {
    if (level) return routeModels(level, this.routable());
    return this.list().flatMap((p) => (p.best ? [`${p.provider}:${p.best}`] : []));
  }

  /** What each level of task would use right now, for Settings. */
  routes(): ModelRoutes {
    const all = this.routable();
    return { light: routeModels("light", all), standard: routeModels("standard", all), heavy: routeModels("heavy", all) };
  }

  /** For Settings and the Keys screen: every provider's usable models and its pick. */
  list(): ProviderModels[] {
    return this.groups().map((g) => {
      const e = this.cache.get(g.provider);
      const models = (e?.ranked ?? []).map((m) => m.id);
      const best = models.find((m) => !this.bad.has(`${g.provider}:${m}`)) ?? null;
      return { provider: g.provider, label: g.label, models, best, ...(e?.error ? { error: e.error } : {}) };
    });
  }
}

const catalogs = new WeakMap<KeyStore, ModelCatalog>();

/** One catalog per key store, shared by the API and every project's engine. */
export function catalogFor(keys: KeyStore): ModelCatalog {
  let c = catalogs.get(keys);
  if (!c) {
    c = new ModelCatalog(keys);
    catalogs.set(keys, c);
  }
  return c;
}
