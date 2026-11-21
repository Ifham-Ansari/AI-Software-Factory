// The engine's conversation (OpenAI chat format) and how it is shrunk to fit a model's context. Free tiers have
// small token-per-minute limits, so old tool output is the first thing to go.

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

/**
 * Shrink a conversation to about `maxTokens`, keeping the system prompt, the first user message (the task), the
 * latest user message, and the most recent steps. Older tool results become a stub first; if that is not enough,
 * the oldest steps are dropped whole (an assistant message together with its tool results, so the history stays
 * valid for the API).
 */
export function compactMessages(messages: ChatMessage[], maxTokens: number, keepRecentResults = 6): ChatMessage[] {
  if (estimateTokens(messages) <= maxTokens) return messages;
  const out = messages.map((m) => ({ ...m })) as ChatMessage[];
  // 1. Stub old tool results (all but the most recent few).
  const toolIdx = out.flatMap((m, i) => (m.role === "tool" ? [i] : []));
  for (const i of toolIdx.slice(0, Math.max(0, toolIdx.length - keepRecentResults))) {
    const m = out[i] as Extract<ChatMessage, { role: "tool" }>;
    if (m.content.length > STUB.length) m.content = STUB;
  }
  if (estimateTokens(out) <= maxTokens) return out;

  // 2. Drop the oldest steps after the first user message, keeping the last two steps.
  const firstUser = out.findIndex((m) => m.role === "user");
  const head = out.slice(0, firstUser + 1);
  let rest = out.slice(firstUser + 1);
  const steps: ChatMessage[][] = [];
  for (const m of rest) {
    if (m.role === "tool" && steps.length) steps[steps.length - 1]!.push(m);
    else steps.push([m]);
  }
  let dropped = 0;
  while (steps.length > 2 && estimateTokens([...head, ...steps.flat()]) > maxTokens) {
    // Never drop a user message that is not the first: it carries new instructions (a resume, an answer).
    const i = steps.findIndex((s) => s[0]!.role !== "user");
    if (i < 0 || i >= steps.length - 2) break;
    steps.splice(i, 1);
    dropped++;
  }
  rest = steps.flat();
  const note: ChatMessage[] = dropped ? [{ role: "user", content: `(${dropped} earlier steps were removed to save tokens. Check files again if you need their state.)` }] : [];
  // A user note right after the first user message would make two user turns in a row; merge it instead.
  if (note.length) {
    const first = head[head.length - 1] as Extract<ChatMessage, { role: "user" }>;
    head[head.length - 1] = { role: "user", content: `${first.content}\n\n${note[0]!.content}` };
  }
  return [...head, ...rest];
}
