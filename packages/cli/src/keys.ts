import { PROVIDERS, providerPreset } from "@asf/core";
import readline from "node:readline/promises";
import { flag, type Parsed } from "./args.ts";
import { CliError } from "./client.ts";

// `asf keys`: the team's API keys for the built-in engine, kept on this computer in ~/.asf/keys.json.
// Each teammate adds their own key once, labelled with their name; AI Software Factory spreads work over all keys
// and switches when one hits its limit. Owner-only: refused inside agent runs.

const USAGE = `asf keys                                   list the team's keys (masked)
asf keys providers                         providers you can use, with where to get a free key
asf keys add <provider> --label <name> [--key <key>] [--base-url <url>]
                                           add a key (asks for it when --key is left out)
asf keys test [id]                         check keys with the provider (uses no tokens)
asf keys remove <id>                       remove a key`;

async function readSecret(prompt: string): Promise<string> {
  if (!process.stdin.isTTY) {
    const chunks: Buffer[] = [];
    for await (const c of process.stdin) chunks.push(c as Buffer);
    return Buffer.concat(chunks).toString("utf8").trim();
  }
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  try {
    return (await rl.question(prompt)).trim();
  } finally {
    rl.close();
  }
}

export async function keysCommand(p: Parsed): Promise<number> {
  if (process.env.ASF_RUN || process.env.ASF_TOKEN) throw new CliError("`asf keys` is for the owner; it is not available inside agent runs.", 3);
  const { KeyStore, listModels } = await import("@asf/server");
  const store = new KeyStore();
  const sub = p.positional[1] ?? "list";
  const json = Boolean(p.flags.json);

  if (sub === "list") {
    const views = store.views();
    if (json) console.log(JSON.stringify(views, null, 2));
    else if (!views.length) console.log("No keys yet. Add one: asf keys add <provider> --label <your name>   (see `asf keys providers`)");
    else
      for (const k of views)
        console.log(
          `${k.id}  ${k.provider.padEnd(10)} ${k.label.padEnd(16)} ${k.masked.padEnd(9)} ${k.invalid ? `INVALID: ${k.invalid}` : "ok"}  today: ${k.usageToday.requests} requests, ${(k.usageToday.input + k.usageToday.output).toLocaleString()} tokens`,
        );
    return 0;
  }
  if (sub === "providers") {
    for (const pr of PROVIDERS) console.log(`${pr.id.padEnd(11)} ${pr.label.padEnd(28)} ${pr.keyUrl ?? (pr.keyless ? "no key needed" : "")}\n            ${pr.note}`);
    return 0;
  }
  if (sub === "add") {
    const provider = p.positional[2];
    if (!provider) throw new CliError(`usage:\n${USAGE}`, 2);
    const preset = providerPreset(provider);
    if (!preset) throw new CliError(`unknown provider "${provider}". Run \`asf keys providers\`.`, 2);
    const label = flag(p, "label");
    if (!label) throw new CliError("say whose key it is: --label <name>", 2);
    let key = flag(p, "key") ?? "";
    if (!key && !preset.keyless) {
      if (preset.keyUrl) console.log(`Create a key at ${preset.keyUrl}`);
      key = await readSecret(`Paste the ${preset.label} key for ${label}: `);
    }
    try {
      const k = store.add({ provider, label, key, baseUrl: flag(p, "base-url") });
      console.log(`Added ${k.id} (${provider}, ${label}). Test it with: asf keys test ${k.id}`);
    } catch (e) {
      throw new CliError((e as Error).message, 1);
    }
    return 0;
  }
  if (sub === "remove") {
    const id = p.positional[2];
    if (!id) throw new CliError("usage: asf keys remove <id>", 2);
    if (!store.remove(id)) throw new CliError(`no key ${id}`, 1);
    console.log(`Removed ${id}.`);
    return 0;
  }
  if (sub === "test") {
    const id = p.positional[2];
    const keys = store.list().filter((k) => !id || k.id === id);
    if (!keys.length) throw new CliError(id ? `no key ${id}` : "no keys to test", 1);
    let bad = 0;
    for (const k of keys) {
      const r = await listModels(store.baseUrl(k), k.key);
      if (r.ok) {
        if (k.invalid) store.setInvalid(k.id, null);
        console.log(`[ok  ] ${k.id} ${k.provider} (${k.label}): ${r.models.length} models`);
      } else {
        bad++;
        if (r.error.kind === "auth") store.setInvalid(k.id, r.error.message);
        console.log(`[FAIL] ${k.id} ${k.provider} (${k.label}): ${r.error.message}`);
      }
    }
    return bad ? 1 : 0;
  }
  throw new CliError(`usage:\n${USAGE}`, 2);
}
