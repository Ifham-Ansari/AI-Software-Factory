// The engine's conversation (OpenAI chat format) and how it is shrunk to fit a model's context. Free tiers have
// small token-per-minute limits. What goes first is what the agent can get back from disk: old tool output, then
// the content of files it already wrote (a 30k-character mockup in a Write call). Whole steps are dropped last, and
// the agent is told what they did, so it never starts its work over.

export interface ToolCallMsg {
  id: string;
  type: "function";
  function: { name: string; arguments: string };
}

export type ChatMessage =
  | { role: "system"; content: string }
  | { role: "user"; content: string }
  | { role: "assistant"; content: string | null; tool_calls?: ToolCallMsg[] }
  | { role: "tool"; tool_call_id: string; content: string };

/** Rough token count (about 4 characters per token): good enough to decide what to trim. */
export function estimateTokens(messages: ChatMessage[]): number {
  let chars = 0;
  for (const m of messages) {
    chars += (m.content ?? "").length + 8;
    if (m.role === "assistant") for (const c of m.tool_calls ?? []) chars += c.function.name.length + c.function.arguments.length + 16;
  }
  return Math.ceil(chars / 4);
}

const STUB = "(output trimmed to save tokens; run the tool again if you need it)";
/** Tool-call arguments longer than this are shortened once the call has run. */
const BIG_ARG = 600;

function parseArgs(call: ToolCallMsg): Record<string, unknown> | null {
  try {
    const v = JSON.parse(call.function.arguments);
    return v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

/**
 * A call that has already run, with its big arguments shortened: the file content of a Write or an Edit (it is on
 * disk; the agent can Read it), or a long command. Small calls are returned as they are.
 */
export function shrinkToolCall(call: ToolCallMsg): ToolCallMsg {
  if (call.function.arguments.length <= BIG_ARG) return call;
  const args = parseArgs(call);
  if (!args) return { ...call, function: { ...call.function, arguments: JSON.stringify({ note: "(arguments trimmed to save tokens)" }) } };
  const file = typeof args.file_path === "string" ? args.file_path : "the file";
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(args)) {
    if (typeof v === "string" && v.length > BIG_ARG && (k === "content" || k === "new_string" || k === "old_string"))
      out[k] = `(${v.length} characters, already ${k === "content" ? "written to" : "applied in"} ${file}; Read the file to see them)`;
    else if (typeof v === "string" && v.length > BIG_ARG) out[k] = `${v.slice(0, 300)}… (${v.length - 300} more characters trimmed)`;
    else out[k] = v;
  }
  return { ...call, function: { ...call.function, arguments: JSON.stringify(out) } };
}

const ASF_ACTION = /(?:^|[\s;&|(])asf\s+((?:doc|plan|task|ask|review|qa|bug|reply|decision)\b[^\n;&|]*)/;

/**
 * What the agent already did in these messages, in a few lines: files it wrote or edited, the asf commands that
 * changed the board, and its latest checklist. Null when there is nothing to report.
 */
export function progressSummary(messages: ChatMessage[]): string | null {
  const files: string[] = [];
  const actions: string[] = [];
  type Todo = { content?: unknown; status?: unknown };
  let todos = null as Todo[] | null;
  for (const m of messages) {
    if (m.role !== "assistant") continue;
    for (const c of m.tool_calls ?? []) {
      const args = parseArgs(c) ?? {};
      const name = c.function.name;
      if ((name === "Write" || name === "Edit") && typeof args.file_path === "string") {
        const f = args.file_path.replace(/\\/g, "/");
        const at = files.indexOf(f);
        if (at >= 0) files.splice(at, 1);
        files.push(f);
      } else if (name === "Bash" && typeof args.command === "string") {
        const a = ASF_ACTION.exec(args.command)?.[1];
        if (a) {
          const short = `asf ${a.trim().replace(/\s+/g, " ").slice(0, 80)}`;
          if (!actions.includes(short)) actions.push(short);
        }
      } else if (name === "TodoWrite" && Array.isArray(args.todos)) todos = args.todos as Todo[];
    }
  }
  if (!files.length && !actions.length && !todos?.length) return null;
  const lines: string[] = [];
  if (files.length) lines.push(`Files you already wrote or edited: ${files.slice(-40).join(", ")}${files.length > 40 ? ` (and ${files.length - 40} more)` : ""}.`);
  if (actions.length) lines.push(`asf commands you already ran: ${actions.slice(-15).join("; ")}.`);
  if (todos?.length)
    lines.push(`Your checklist:\n${todos.slice(0, 30).map((t) => `- [${t.status === "completed" ? "x" : " "}] ${String(t.content ?? "")}`).join("\n")}`);
  lines.push("Do not redo finished work: if you are unsure whether a file is complete, Read it, then continue with what is left.");
  return lines.join("\n");
}

/** Tool results further back than this many are stale: shortened on every request, not only when one is too big. */
export const STALE_AFTER = 6;
/**
 * Stale results are shortened this many at a time, so the start of the conversation stays the same for several
 * requests in a row: providers that cache a repeated prompt start (Gemini, Groq, OpenRouter, DeepSeek, …) reuse it.
 */
export const STALE_CHUNK = 4;
/** A stale result longer than this keeps only its first line (short ones, like "Wrote src/app.ts.", stay whole). */
const STALE_MAX_CHARS = 300;

/**
 * A file read whose latest copy stays whole, or null: the project's documents (`.asf/docs/`: the PRD, the
 * architecture, contracts), which planning runs work from all along (trimmed, an agent re-read its PRD seven
 * times in one run), and with the short instructions the agent's SKILL.md files. References, templates, and
 * source files are trimmed like any other output.
 */
function keptRead(call: ToolCallMsg | undefined, skills: boolean): string | null {
  if (!call || call.function.name !== "Read") return null;
  const raw = parseArgs(call)?.file_path;
  if (typeof raw !== "string") return null;
  const f = raw.replace(/\\/g, "/");
  if (/(^|\/)\.asf\/docs\//.test(f)) return f.replace(/^.*?\.asf\/docs\//, ".asf/docs/");
  return skills && /\/skills\/[^/]+\/SKILL\.md$/i.test(f) ? f : null;
}

/**
 * Every request resends the whole conversation, so a file read or a test run early in a run is paid for again on
 * every later turn. Results older than the latest STALE_AFTER keep only their first line (the agent can run the
 * tool again; files are on disk), and calls that already ran lose their big arguments (written content is on
 * disk). The latest read of each project document (`.asf/docs/`) stays whole, and with the short instructions
 * (`keepSkillReads`) the latest read of each SKILL.md: they are what the agent works from. With the full
 * instructions the skills are in the system prompt already, so reading them again is trimmed like any other file.
 * The history itself is not changed.
 *
 * This is the same trimming compactMessages does when a request no longer fits, done on every request, so a run
 * does not send everything until it hits the limit and then almost nothing.
 */
export function trimStale(
  messages: ChatMessage[],
  opts: { keepSkillReads?: boolean; keep?: number; chunk?: number } = {},
): ChatMessage[] {
  const { keep = STALE_AFTER, chunk = STALE_CHUNK } = opts;
  const toolIdx = messages.flatMap((m, i) => (m.role === "tool" ? [i] : []));
  const stale = Math.floor(Math.max(0, toolIdx.length - keep) / chunk) * chunk;
  if (stale === 0) return messages;
  const last = toolIdx[stale - 1]!;
  const calls = new Map<string, ToolCallMsg>();
  for (const m of messages) if (m.role === "assistant") for (const c of m.tool_calls ?? []) calls.set(c.id, c);
  // The latest read of each project document (and, with the short instructions, of each skill) stays whole.
  const latest = new Map<string, string>();
  for (const m of messages) {
    const f = m.role === "tool" ? keptRead(calls.get(m.tool_call_id), Boolean(opts.keepSkillReads)) : null;
    if (f && m.role === "tool") latest.set(f, m.tool_call_id);
  }
  const instructions = new Set(latest.values());
  return messages.map((m, i) => {
    if (i > last) return m;
    if (m.role === "tool" && m.content.length > STALE_MAX_CHARS && !instructions.has(m.tool_call_id)) {
      const first = m.content.trimStart().split("\n", 1)[0]!.slice(0, 120);
      return { ...m, content: `${first}\n(${m.content.length} characters; trimmed to save tokens. Run the tool again if you need them.)` };
    }
    if (m.role === "assistant" && m.tool_calls?.length) return { ...m, tool_calls: m.tool_calls.map(shrinkToolCall) };
    return m;
  });
}

/**
 * Shrink a conversation to about `maxTokens`, keeping the system prompt, the first user message (the task), the
 * latest user message, and the most recent steps. In order, until it fits: older tool results become a stub; the
 * big arguments of calls that already ran are shortened (older ones first); the oldest steps are dropped whole (an
 * assistant message together with its tool results, so the history stays valid), with a note of what they did.
 */
export function compactMessages(messages: ChatMessage[], maxTokens: number, keepRecentResults = 6): ChatMessage[] {
  if (estimateTokens(messages) <= maxTokens) return messages;
  const out = messages.map((m) => ({ ...m })) as ChatMessage[];
  const fits = () => estimateTokens(out) <= maxTokens;
  const toolIdx = out.flatMap((m, i) => (m.role === "tool" ? [i] : []));
  const stubResults = (keep: number) => {
    for (const i of toolIdx.slice(0, Math.max(0, toolIdx.length - keep))) {
      const m = out[i] as Extract<ChatMessage, { role: "tool" }>;
      if (m.content.length > STUB.length) m.content = STUB;
    }
  };
  const assistantIdx = out.flatMap((m, i) => (m.role === "assistant" && m.tool_calls?.length ? [i] : []));
  const shrinkCalls = (idx: number[]) => {
    for (const i of idx) {
      const m = out[i] as Extract<ChatMessage, { role: "assistant" }>;
      m.tool_calls = m.tool_calls!.map(shrinkToolCall);
    }
  };

  // 1. Stub old tool results (all but the most recent few).
  stubResults(keepRecentResults);
  if (fits()) return out;
  // 2. Shorten the big arguments of every call but the latest (its content is on disk now).
  shrinkCalls(assistantIdx.slice(0, -1));
  if (fits()) return out;
  // 3. The latest call too, and all but the last two tool results.
  shrinkCalls(assistantIdx.slice(-1));
  stubResults(2);
  if (fits()) return out;

  // 4. Drop the oldest steps after the first user message, keeping the last two steps.
  const firstUser = out.findIndex((m) => m.role === "user");
  const head = out.slice(0, firstUser + 1);
  const steps: ChatMessage[][] = [];
  for (const m of out.slice(firstUser + 1)) {
    if (m.role === "tool" && steps.length) steps[steps.length - 1]!.push(m);
    else steps.push([m]);
  }
  const droppedSteps: ChatMessage[][] = [];
  while (steps.length > 2 && estimateTokens([...head, ...steps.flat()]) > maxTokens) {
    // Never drop a user message that is not the first: it carries new instructions (a resume, an answer).
    const i = steps.findIndex((s) => s[0]!.role !== "user");
    if (i < 0 || i >= steps.length - 2) break;
    droppedSteps.push(...steps.splice(i, 1));
  }
  if (droppedSteps.length) {
    // Tell the agent what the dropped steps did, so it carries on instead of starting over. The note joins the
    // first user message (two user turns in a row are not allowed everywhere).
    const did = progressSummary(droppedSteps.flat());
    const note = `(${droppedSteps.length} earlier steps were removed to save tokens.${did ? `\n${did}` : " Check files again if you need their state."})`;
    const first = head[head.length - 1] as Extract<ChatMessage, { role: "user" }>;
    head[head.length - 1] = { role: "user", content: `${first.content}\n\n${note}` };
  }
  return [...head, ...steps.flat()];
}
