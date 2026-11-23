import { useMemo, useState } from "react";
import { Badge, Empty, Loadable, Modal, PageHeader, toast, toastError } from "../components/ui";
import { api } from "../lib/api";
import { fmtTokens, plural } from "../lib/format";
import { useEngine, useKeyAction, useProject } from "../lib/queries";
import { href } from "../lib/router";
import type { KeyView, ProviderModels, ProviderPreset } from "../lib/types";

// The team's API keys for the built-in engine. They are kept on this computer (~/.asf/keys.json), shared by
// every project here, and never shown again in full: the server only ever returns the last four characters.

const until = (ms: number) => new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

const worksText = (label: string, r: { models?: number; best?: string | null }) =>
  `${label}'s key works (${r.models} models)${r.best ? `. Best model: ${r.best}, used automatically.` : ""}`;

/** Each key's provider pick (custom servers by key id, named providers by provider). */
function bestByKey(keys: KeyView[], models: ProviderModels[]): Record<string, string | null> {
  return Object.fromEntries(keys.map((k) => [k.id, models.find((m) => m.provider === (k.provider === "custom" ? k.id : k.provider))?.best ?? null]));
}

function KeyStatus({ k }: { k: KeyView }) {
  if (k.invalid)
    return (
      <Badge tone="danger" title={k.invalid}>
        rejected
      </Badge>
    );
  if (k.cooldownUntil) return <Badge tone="warn">limited until {until(k.cooldownUntil)}</Badge>;
  if (k.modelsLimited)
    return (
      <Badge tone="ok" title="Some of this key's models are at their own limit; its other models keep working.">
        ready · {plural(k.modelsLimited, "model")} resting
      </Badge>
    );
  return <Badge tone="ok">ready</Badge>;
}

export function KeysScreen({ pid }: { pid: string }) {
  const engine = useEngine();
  const project = useProject(pid);
  const usesEngine = project.data?.settings.engine === "builtin";
  return (
    <div className="max-w-5xl">
      <PageHeader title="API keys" kicker="built-in engine · your team's own keys" />
      <p className="mb-4 max-w-[75ch] text-[13px] text-ink-2">
        With the built-in engine, agents run on free API tiers (Gemini, Groq, OpenRouter, Mistral, Cerebras) or on a model
        running on this computer (Ollama, LM Studio), with no Claude subscription. Each teammate adds their own key here, labelled
        with their name. Work is spread over every key, and when one reaches its limit the agent carries on with the next.
      </p>
      <div
        className={`mb-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border px-4 py-3 text-[13px] ${usesEngine ? "border-rule bg-surface" : "border-[color-mix(in_srgb,var(--warn)_40%,transparent)] bg-warn-soft"}`}
        data-testid="engine-status"
      >
        <span>
          This project runs its agents on{" "}
          <strong>{usesEngine ? "the built-in engine (these keys)" : "Claude Code (your Claude subscription)"}</strong>.
          {!usesEngine && engine.data && !engine.data.claudeFound && " Claude Code is not installed on this computer."}
        </span>
        <a className="btn btn-sm" href={href(pid, "settings")}>
          {usesEngine ? "Models and engine settings" : "Switch to the built-in engine"}
        </a>
      </div>
      <Loadable q={engine} rows={6}>
        {(e) => (
          <>
            <AddKeyForm providers={e.providers} />
            <KeyList keys={e.keys} providers={e.providers} best={bestByKey(e.keys, e.models ?? [])} />
            <TeamUsage keys={e.keys} />
          </>
        )}
      </Loadable>
      <p className="mt-8 max-w-[75ch] text-[12.5px] text-ink-3" data-testid="keys-terms">
        Each key belongs to the teammate who added it, and its use is covered by their provider's terms. Some providers do not
        allow a key to be shared, so check before adding a key for someone else. Keys are stored only on this computer, are never
        shown in full again, and agents cannot read them.
      </p>
    </div>
  );
}

function AddKeyForm({ providers }: { providers: ProviderPreset[] }) {
  const [provider, setProvider] = useState(providers[0]?.id ?? "custom");
  const [label, setLabel] = useState("");
  const [key, setKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const preset = providers.find((p) => p.id === provider);
  const needsUrl = provider === "custom" || Boolean(preset?.keyless) || Boolean(preset?.needsBaseUrl);
  const groups: [string, ProviderPreset[]][] = [
    ["Free tiers", providers.filter((p) => (p.tier ?? "free") === "free" && p.id !== "custom")],
    ["On this computer", providers.filter((p) => p.tier === "local")],
    ["Trial credit only", providers.filter((p) => p.tier === "trial")],
    ["Other", providers.filter((p) => p.id === "custom")],
  ];
  const add = useKeyAction<{ provider: string; label: string; key: string; baseUrl?: string }, KeyView>("POST", () => "/api/keys");
  return (
    <form
      className="card mb-6 flex flex-col gap-3 px-5 py-4"
      data-testid="add-key"
      onSubmit={(ev) => {
        ev.preventDefault();
        add.mutate(
          { provider, label, key, baseUrl: needsUrl ? baseUrl || preset?.baseUrl : undefined },
          {
            onSuccess: async (k) => {
              setKey("");
              toast(`Key added for ${k.label}. Checking it…`);
              try {
                const r = await api<{ ok: boolean; models?: number; best?: string | null; error?: string }>("POST", `/api/keys/${k.id}/test`, {});
                toast(r.ok ? worksText(k.label, r) : `${k.label}'s key did not work: ${r.error}`, r.ok ? "ok" : "danger");
              } catch (err) {
                toastError(err);
              }
            },
            onError: toastError,
          },
        );
      }}
    >
      <div className="text-[14px] font-semibold">Add a key</div>
      <div className="grid grid-cols-[200px_200px_minmax(0,1fr)_auto] items-end gap-2 max-[1100px]:grid-cols-1">
        <label className="flex flex-col gap-1 text-[12px] text-ink-2">
          Provider
          <select
            className="field"
            value={provider}
            onChange={(ev) => {
              setProvider(ev.target.value);
              // A URL with the owner's own part to fill in starts from the provider's template.
              setBaseUrl(providers.find((p) => p.id === ev.target.value)?.needsBaseUrl ? (providers.find((p) => p.id === ev.target.value)?.baseUrl ?? "") : "");
            }}
            aria-label="Provider"
          >
            {groups
              .filter(([, list]) => list.length)
              .map(([title, list]) => (
                <optgroup key={title} label={title}>
                  {list.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                    </option>
                  ))}
                </optgroup>
              ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-[12px] text-ink-2">
          Whose key
          <input className="field" placeholder="e.g. Ayesha" value={label} onChange={(ev) => setLabel(ev.target.value)} maxLength={60} required aria-label="Whose key" />
        </label>
        {preset?.keyless ? (
          <div className="pb-2 text-[12.5px] text-ink-3">{preset.tier === "local" ? "No key needed for a model running on this computer." : "No key needed: it works anonymously."}</div>
        ) : (
          <label className="flex flex-col gap-1 text-[12px] text-ink-2">
            API key{preset?.keyOptional ? " (optional: raises the limit)" : ""}
            <input
              className="field mono text-[12px]"
              type="password"
              autoComplete="off"
              spellCheck={false}
              placeholder={preset?.keyOptional ? "leave empty to use it without a key" : "paste the key"}
              value={key}
              onChange={(ev) => setKey(ev.target.value)}
              required={!preset?.keyOptional}
              aria-label="API key"
            />
          </label>
        )}
        <button className="btn btn-primary" disabled={add.isPending}>
          Add key
        </button>
      </div>
      {needsUrl && (
        <label className="flex flex-col gap-1 text-[12px] text-ink-2">
          Base URL{" "}
          {provider === "custom"
            ? "(OpenAI-compatible, usually ending in /v1)"
            : preset?.needsBaseUrl
              ? "(replace the {…} part with your own, e.g. your account id)"
              : "(change it if the server runs on another port)"}
          <input
            className="field mono text-[12px]"
            placeholder={preset?.baseUrl || "https://example.com/v1"}
            value={baseUrl}
            onChange={(ev) => setBaseUrl(ev.target.value)}
            required={provider === "custom" || Boolean(preset?.needsBaseUrl)}
            aria-label="Base URL"
          />
        </label>
      )}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12.5px] text-ink-2">
        <span>{preset?.note}</span>
        {preset?.keyUrl && (
          <a className="font-medium text-accent underline-offset-2 hover:underline" href={preset.keyUrl} target="_blank" rel="noreferrer noopener">
            {preset.tier === "trial" ? "Get a key ↗" : "Get a free key ↗"}
          </a>
        )}
      </div>
    </form>
  );
}

function KeyList({ keys, providers, best }: { keys: KeyView[]; providers: ProviderPreset[]; best: Record<string, string | null> }) {
  const [removing, setRemoving] = useState<KeyView | null>(null);
  const remove = useKeyAction<string>("DELETE", (id) => `/api/keys/${id}`);
  const test = useKeyAction<string, { ok: boolean; models?: number; best?: string | null; error?: string }>("POST", (id) => `/api/keys/${id}/test`);
  const name = (id: string) => providers.find((p) => p.id === id)?.label ?? id;
  if (!keys.length)
    return (
      <Empty title="No keys yet">
        Add a free key above. One is enough to start; each extra key (yours or a teammate's) adds to what the team can do per day.
      </Empty>
    );
  return (
    <>
      <ul className="card flex flex-col divide-y divide-rule overflow-hidden" data-testid="keys-list">
        {keys.map((k) => (
          <li key={k.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3" data-testid={`key-${k.id}`}>
            <div className="min-w-[180px] flex-1">
              <div className="text-[13.5px] font-medium">
                {k.label} <span className="font-normal text-ink-3">· {name(k.provider)}</span>
              </div>
              <div className="mono text-[11.5px] text-ink-3">
                {k.masked} · {plural(k.usageToday.requests, "request")} today · {fmtTokens(k.usageToday.input + k.usageToday.output)} tokens
              </div>
              {!k.invalid && best[k.id] && (
                <div className="mt-0.5 text-[12px] text-ink-2" data-testid={`key-best-${k.id}`}>
                  best model: <span className="mono text-[11.5px] text-accent">{best[k.id]}</span>
                </div>
              )}
              {k.invalid && <div className="mono mt-0.5 text-[11.5px] text-danger">{k.invalid}</div>}
            </div>
            <KeyStatus k={k} />
            <button
              className="btn btn-sm"
              disabled={test.isPending}
              onClick={() =>
                test.mutate(k.id, {
                  onSuccess: (r) => toast(r.ok ? worksText(k.label, r) : `${k.label}'s key did not work: ${r.error}`, r.ok ? "ok" : "danger"),
                  onError: toastError,
                })
              }
            >
              Test
            </button>
            <button className="btn btn-sm" onClick={() => setRemoving(k)}>
              Remove
            </button>
          </li>
        ))}
      </ul>
      <Modal
        open={removing !== null}
        onClose={() => setRemoving(null)}
        title={`Remove ${removing?.label}'s ${removing ? name(removing.provider) : ""} key?`}
        testId="remove-key"
        footer={
          <>
            <button className="btn" onClick={() => setRemoving(null)}>
              Keep it
            </button>
            <button
              className="btn btn-danger"
              onClick={() =>
                removing &&
                remove.mutate(removing.id, {
                  onSuccess: () => {
                    toast("Key removed");
                    setRemoving(null);
                  },
                  onError: toastError,
                })
              }
            >
              Remove key
            </button>
          </>
        }
      >
        AI Software Factory forgets this key; agents carry on with the team's other keys. The key still exists at the provider:
        revoke it there if it should stop working everywhere.
      </Modal>
    </>
  );
}

/** Today's usage per teammate, so everyone sees whose free allowance went where. */
function TeamUsage({ keys }: { keys: KeyView[] }) {
  const rows = useMemo(() => {
    const by = new Map<string, { requests: number; tokens: number; keys: number }>();
    for (const k of keys) {
      const r = by.get(k.label) ?? { requests: 0, tokens: 0, keys: 0 };
      by.set(k.label, { requests: r.requests + k.usageToday.requests, tokens: r.tokens + k.usageToday.input + k.usageToday.output, keys: r.keys + 1 });
    }
    return [...by.entries()].sort((a, b) => b[1].tokens - a[1].tokens);
  }, [keys]);
  if (rows.length < 2) return null;
  return (
    <div className="mt-6" data-testid="team-usage">
      <h2 className="section-title mb-2">TODAY, PER TEAMMATE</h2>
      <ul className="flex flex-col gap-1 text-[13px]">
        {rows.map(([label, r]) => (
          <li key={label} className="flex gap-3">
            <span className="w-40 font-medium">{label}</span>
            <span className="mono text-[12px] text-ink-2">
              {plural(r.keys, "key")} · {plural(r.requests, "request")} · {fmtTokens(r.tokens)} tokens
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
