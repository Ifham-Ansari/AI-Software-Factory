// Tools the built-in engine offers the model. They use Claude Code's tool names and parameter names on purpose:
// the guard (guard.ts), the feed summaries (stream.ts), and the dashboard transcript all understand them already.

export interface ToolDef {
  type: "function";
  function: { name: string; description: string; parameters: Record<string, unknown> };
}

const obj = (properties: Record<string, unknown>, required: string[]) => ({ type: "object", properties, required, additionalProperties: false });
const str = (description: string) => ({ type: "string", description });
const int = (description: string) => ({ type: "integer", description });
const bool = (description: string) => ({ type: "boolean", description });

export const ENGINE_TOOLS: ToolDef[] = [
  {
    type: "function",
    function: {
      name: "Read",
      description: "Read a text file. Returns numbered lines. Use offset/limit for large files.",
      parameters: obj({ file_path: str("Path to the file (relative to the working folder, or absolute)"), offset: int("First line to read, 1-based"), limit: int("Number of lines to read (default 2000)") }, ["file_path"]),
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

/** Caps that keep one tool result from flooding a small model's context. */
export const TOOL_CAPS = {
  readLines: 2000,
  readChars: 60_000,
  bashChars: 30_000,
  listResults: 200,
  bashTimeoutSeconds: 300,
  bashMaxTimeoutSeconds: 600,
};

/** Added before the role's skills: how to work with these tools. Kept short, every request pays for it. */
export const ENGINE_PREAMBLE = [
  "# How to work in this run",
  "",
  "You act only through tools: Read, Write, Edit, Bash, Grep, Glob, TodoWrite. Call one or more tools per turn and wait for",
  "their results. Read a file before you Edit it. Run the `asf` CLI with Bash. Paths are relative to your working folder.",
  "When the work is done (or you are blocked and have said so with the asf CLI), reply with a one-line summary and no tool call: that ends the run.",
  "",
].join("\n");
