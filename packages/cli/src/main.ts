#!/usr/bin/env node
import { parseArgs } from "./args.ts";
import { AGENT_COMMANDS, runAgentCommand } from "./agent-commands.ts";
import { CliError } from "./client.ts";

const HELP = `asf — AI Software Factory: your local AI software team (runs on your own Claude Code)

Owner commands:
  asf setup [--uninstall]        install the asf command so it works from any folder
  asf init [path]                make a folder an AI Software Factory project (adds one hidden .asf folder)
  asf doctor [--login] [--keys]  check prerequisites (node, pnpm, git, docker, uv, claude, API keys)
  asf up [--port N] [--no-open]  start the local server + dashboard (127.0.0.1 only)
  asf status                     phase, tasks, agents, quota for the current project
  asf pause | resume             stop/start scheduling new agent runs
  asf stop                       kill switch: stop every agent process now
  asf logs <agent|task> [-f]     recent events for an agent (backend-1) or task (T012)
  asf keys [list|add|test|remove|providers]
                                 the team's API keys for the built-in engine (free tiers, local models)

Agent commands (used by agents inside runs; see .asf/skills/team-protocol/references/asf-cli.md):
  whoami, task show|list|start|block|unblock|done, progress, msg, ask, inbox, reply,
  decision, doc list|show|submit, plan check|submit, review ..., qa pass|fail, bug create

Add --json for machine-readable output.
Exit codes: 0 ok, 1 refused, 2 invalid arguments, 3 not allowed, 4 server unreachable.`;

async function main(argv: string[]): Promise<number> {
  const p = parseArgs(argv);
  const group = p.positional[0];
  const json = Boolean(p.flags.json);
  if (!group || group === "help" || p.flags.help) {
    console.log(HELP);
    return 0;
  }
  if (group === "hook") {
    const { preToolUseHook } = await import("./hook.ts");
    if (p.positional[1] === "pre-tool-use") return preToolUseHook();
    throw new CliError("usage: asf hook pre-tool-use", 2);
  }
  if (AGENT_COMMANDS.has(group)) {
    const r = await runAgentCommand(p);
    if (json) console.log(JSON.stringify({ ok: r.ok, text: r.text, data: r.data }, null, 2));
    else if (r.exit) console.error(r.text);
    else console.log(r.text);
    return r.exit ?? 0;
  }
  const human = await import("./human.ts");
  return human.run(group, p);
}

main(process.argv.slice(2)).then(
  (code) => {
    process.exitCode = code;
  },
  (e) => {
    if (e instanceof CliError) {
      if (process.argv.includes("--json")) console.log(JSON.stringify({ ok: false, error: e.message, exit: e.exit }));
      else console.error(`asf: ${e.message}`);
      process.exitCode = e.exit;
    } else {
      console.error(`asf: ${(e as Error)?.stack ?? e}`);
      process.exitCode = 1;
    }
  },
);
