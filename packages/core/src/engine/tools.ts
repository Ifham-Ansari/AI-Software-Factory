// Tools the built-in engine offers the model. They use Claude Code's tool names and parameter names on purpose:
// the guard (guard.ts), the feed summaries (stream.ts), and the dashboard transcript all understand them already.

export interface ToolDef {
  type: "function";
  function: { name: string; description: string; parameters: Record<string, unknown> };
}

// No additionalProperties: some providers (Gemini) reject schema keywords outside a small subset.
const obj = (properties: Record<string, unknown>, required: string[]) => ({ type: "object", properties, required });
const str = (description: string) => ({ type: "string", description });
const int = (description: string) => ({ type: "integer", description });
const bool = (description: string) => ({ type: "boolean", description });

export const ENGINE_TOOLS: ToolDef[] = [
  {
    type: "function",
    function: {
      name: "Read",
      description: "Read a text file. Returns numbered lines. Use offset/limit for large files.",
      parameters: obj({ file_path: str("Path to the file (relative to the working folder, or absolute)"), offset: int("First line to read, 1-based"), limit: int("Number of lines to read (default 800)") }, ["file_path"]),
    },
  },
  {
    type: "function",
    function: {
      name: "Write",
      description: "Create or overwrite a file with the given content. Parent folders are created.",
      parameters: obj({ file_path: str("Path to the file"), content: str("The full file content") }, ["file_path", "content"]),
    },
  },
  {
    type: "function",
    function: {
      name: "Edit",
      description: "Replace text in a file. old_string must match the file exactly (including indentation) and occur once, unless replace_all is true. Read the file first.",
      parameters: obj(
        { file_path: str("Path to the file"), old_string: str("Exact text to replace"), new_string: str("Replacement text"), replace_all: bool("Replace every occurrence") },
        ["file_path", "old_string", "new_string"],
      ),
    },
  },
  {
    type: "function",
    function: {
      name: "Bash",
      description:
        "Run a bash command in the working folder and return its output and exit code. Use it for the asf CLI, tests, builds, and git status. For a server or watcher that keeps running, set run_in_background.",
      parameters: obj(
        {
          command: str("The command"),
          timeout: int("Seconds before the command is stopped (default 300, max 600)"),
          run_in_background: bool("Start it in the background and return at once (for servers)"),
        },
        ["command"],
      ),
    },
  },
  {
    type: "function",
    function: {
      name: "Grep",
      description: "Search file contents with a regular expression. Skips node_modules, .git, and virtual environments.",
      parameters: obj(
        {
          pattern: str("Regular expression"),
          path: str("File or folder to search (default: the working folder)"),
          glob: str("Only files matching this glob, e.g. **/*.ts"),
          output_mode: { type: "string", enum: ["files_with_matches", "content", "count"], description: "What to return (default files_with_matches)" },
          "-i": bool("Case insensitive"),
        },
        ["pattern"],
      ),
    },
  },
  {
    type: "function",
    function: {
      name: "Glob",
      description: "Find files by glob pattern, newest first.",
      parameters: obj({ pattern: str("Glob, e.g. src/**/*.tsx"), path: str("Folder to search (default: the working folder)") }, ["pattern"]),
    },
  },
  {
    type: "function",
    function: {
      name: "TodoWrite",
      description: "Keep your own plan as a checklist the owner can see. Send the whole list each time.",
      parameters: obj(
        {
          todos: {
            type: "array",
            items: obj({ content: str("The step"), status: { type: "string", enum: ["pending", "in_progress", "completed"] }, activeForm: str("The step in -ing form") }, ["content", "status"]),
          },
        },
        ["todos"],
      ),
    },
  },
];

export const ENGINE_TOOL_NAMES = ENGINE_TOOLS.map((t) => t.function.name);

/**
 * Caps that keep one tool result from flooding a small model's context. Free tiers count every token of every
 * request against small per-minute limits, so results are kept short and the model pages through big files.
 */
export const TOOL_CAPS = {
  readLines: 800,
  readChars: 30_000,
  bashChars: 12_000,
  listResults: 100,
  bashTimeoutSeconds: 300,
  bashMaxTimeoutSeconds: 600,
};

const TOOL_ALIASES: Record<string, string> = {
  read: "Read",
  read_file: "Read",
  view: "Read",
  cat: "Read",
  write: "Write",
  write_file: "Write",
  create_file: "Write",
  edit: "Edit",
  edit_file: "Edit",
  str_replace: "Edit",
  replace: "Edit",
  bash: "Bash",
  shell: "Bash",
  run: "Bash",
  run_command: "Bash",
  execute_command: "Bash",
  terminal: "Bash",
  grep: "Grep",
  search: "Grep",
  search_files: "Grep",
  glob: "Glob",
  find_files: "Glob",
  list_files: "Glob",
  todowrite: "TodoWrite",
  todo_write: "TodoWrite",
  todo: "TodoWrite",
};

const ARG_ALIASES: Record<string, Record<string, string>> = {
  Read: { path: "file_path", file: "file_path", filename: "file_path" },
  Write: { path: "file_path", file: "file_path", filename: "file_path", text: "content", contents: "content" },
  Edit: { path: "file_path", file: "file_path", old_str: "old_string", new_str: "new_string", old: "old_string", new: "new_string" },
  Bash: { cmd: "command", script: "command" },
  Grep: { regex: "pattern", query: "pattern" },
  Glob: { glob: "pattern" },
};

/**
 * Smaller models often name tools and arguments their own way ("read_file", "path", "cmd"). Map the common
 * variants to the real names, so the guard and the tools see what they expect. Unknown names pass through.
 */
export function normalizeToolCall(name: string, input: Record<string, unknown>): { name: string; input: Record<string, unknown> } {
  const canonical = ENGINE_TOOL_NAMES.find((n) => n.toLowerCase() === name.toLowerCase()) ?? TOOL_ALIASES[name.toLowerCase()] ?? name;
  const aliases = ARG_ALIASES[canonical];
  if (!aliases) return { name: canonical, input };
  const out: Record<string, unknown> = { ...input };
  for (const [from, to] of Object.entries(aliases)) {
    if (out[to] === undefined && out[from] !== undefined) {
      out[to] = out[from];
      delete out[from];
    }
  }
  return { name: canonical, input: out };
}

/**
 * Tool call ids the engine writes into the conversation: 9 letters and digits, the strictest format a provider
 * asks for (Mistral), so a run can move to any provider mid-conversation. Unique across resumed runs because the
 * index is the conversation's length.
 */
export function engineCallId(messageIndex: number, callIndex: number): string {
  return `c${String(messageIndex % 100_000).padStart(5, "0")}x${String(callIndex % 100).padStart(2, "0")}`;
}

/** Added before the role's skills: how to work with these tools. Kept short, every request pays for it. */
export const ENGINE_PREAMBLE = [
  "# How to work in this run",
  "",
  "You act only through tools: Read, Write, Edit, Bash, Grep, Glob, TodoWrite. Call one or more tools per turn and wait for",
  "their results. Read a file before you Edit it. Run the `asf` CLI with Bash. Paths are relative to your working folder.",
  "When the work is done (or you are blocked and have said so with the asf CLI), reply with a one-line summary and no tool call: that ends the run.",
  "",
].join("\n");

/** Sent once when a model stops before using any tool: weaker models sometimes describe the work instead of doing it. */
export const ENGINE_NUDGE =
  "You replied without calling a tool, so nothing has been done yet. Do the task now by calling tools (Read, Write, Edit, Bash, …). Reply without a tool call only when the work is finished.";
