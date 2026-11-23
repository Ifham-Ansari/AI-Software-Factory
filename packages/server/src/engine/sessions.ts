import type { ChatMessage } from "@asf/core";
import fs from "node:fs";
import path from "node:path";

// Built-in engine conversations, one JSON file per session in `.asf/sessions/`, so a run can be resumed (after a
// question, a review round, a usage limit, or a restart) exactly like `claude --resume`. The system prompt is not
// stored: it is rebuilt from the role's skills on every run.

export function sessionFile(dir: string, id: string): string {
  return path.join(dir, `${id.replace(/[^A-Za-z0-9_-]/g, "_")}.json`);
}

export function loadSession(dir: string, id: string): ChatMessage[] | null {
  try {
    const j = JSON.parse(fs.readFileSync(sessionFile(dir, id), "utf8")) as { messages?: ChatMessage[] };
    return Array.isArray(j.messages) ? j.messages.filter((m) => m.role !== "system") : null;
  } catch {
    return null;
  }
}

export function saveSession(dir: string, id: string, messages: ChatMessage[]): void {
  fs.mkdirSync(dir, { recursive: true });
  const file = sessionFile(dir, id);
  const tmp = `${file}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify({ id, updatedAt: new Date().toISOString(), messages: messages.filter((m) => m.role !== "system") }));
  fs.renameSync(tmp, file);
}
