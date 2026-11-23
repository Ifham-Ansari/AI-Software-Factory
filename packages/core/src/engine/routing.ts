import type { ModelClass } from "./models.ts";

// Choosing a model by task, in plain code (no model call decides it). Each run gets a level from what it does:
// answering a teammate is light, a small task is light, sizing a request is standard (on the quick track it writes
// the tasks themselves), planning and architecture are heavy.
// Light runs go to small models first and heavy runs to the largest, so the strongest models' free limits are
// kept for the work that needs them, and the small models' (usually much larger) limits carry the routine work.

export type TaskLevel = "light" | "standard" | "heavy";

export interface LevelInput {
  /** The run's mode: triage, answer, implement, review, architect, … */
  mode: string;
  /** implement, fix, review, verify (planning and answer runs use "implement"). */
  stage: string;
  /** The task's size from the plan (S, M, L), when it has one. */
  size?: string | null;
  /** Earlier runs of this task that ended without finishing. */
  failures?: number;
  /** The owner's stakes for the project ("hobby", "customer-facing", …). */
  stakes?: string | null;
}

const LIGHT_MODES = new Set(["answer"]);
// Triage writes the tasks itself on the quick track and must get them through the plan check: a small model got
// lost there after one refusal.
const STANDARD_MODES = new Set(["triage", "discover", "survey"]);
/** Writing the product, the design, the architecture, or the plan, or untangling a failure: needs the strongest. */
const HEAVY_MODES = new Set(["draft", "revise", "change", "direction", "system", "screens", "architect", "plan", "replan", "ruling", "integrate", "repair", "audit", "journey", "release", "scaffold"]);
const ORDER: TaskLevel[] = ["light", "standard", "heavy"];

const raise = (level: TaskLevel, by: number): TaskLevel => ORDER[Math.min(ORDER.indexOf(level) + by, 2)]!;
const atLeast = (level: TaskLevel, min: TaskLevel): TaskLevel => (ORDER.indexOf(level) >= ORDER.indexOf(min) ? level : min);

/** How demanding a run is. */
export function taskLevel(i: LevelInput): TaskLevel {
  const size = (i.size ?? "").toUpperCase();
  let level: TaskLevel;
  if (LIGHT_MODES.has(i.mode)) level = "light";
  else if (STANDARD_MODES.has(i.mode)) level = "standard";
  else if (HEAVY_MODES.has(i.mode)) level = "heavy";
  // Reviews and checks need judgment: on small models a review of a one-page task looped for 40 turns.
  else if (i.mode === "review" || i.mode === "verify") level = "standard";
  else level = size === "S" ? "light" : size === "L" ? "heavy" : "standard";
  // A task that failed before gets a stronger model; a fix after review is never left to the smallest.
  level = raise(level, Math.min(i.failures ?? 0, 2));
  if (i.stage === "fix" || i.mode === "fix") level = atLeast(level, "standard");
  // Code for real users is not left to the smallest models (answering a teammate still is light).
  if (/customer|regulated/i.test(i.stakes ?? "") && ["implement", "fix", "review", "verify"].includes(i.mode)) level = atLeast(level, "standard");
  return level;
}

export interface RoutableModel {
  /** provider:model */
  ref: string;
  class: ModelClass;
  score: number;
}

const CLASS_ORDER: Record<TaskLevel, ModelClass[]> = {
  heavy: ["large", "medium", "small"],
  standard: ["medium", "large", "small"],
  light: ["small", "medium", "large"],
};

/**
 * The models to try for a run of this level, in order: the preferred size first (best first within it), then
 * the others as backups. A few models per provider and size, so one provider's limits do not fill the list.
 * Standard and complex work never fall back to small models while bigger ones exist: when those are all at their
 * limits the run waits for them (a small model would only loop on work it cannot do).
 */
export function routeModels(level: TaskLevel, models: RoutableModel[], perProviderPerClass = 2, max = 12): string[] {
  const out: string[] = [];
  const bigger = models.some((m) => m.class !== "small");
  const classes = CLASS_ORDER[level].filter((cls) => !(cls === "small" && level !== "light" && bigger));
  for (const cls of classes) {
    const perProvider = new Map<string, number>();
    const inClass = models.filter((m) => m.class === cls).sort((a, b) => b.score - a.score || a.ref.localeCompare(b.ref));
    for (const m of inClass) {
      const provider = m.ref.slice(0, m.ref.indexOf(":"));
      const n = perProvider.get(provider) ?? 0;
      if (n >= perProviderPerClass || out.includes(m.ref)) continue;
      perProvider.set(provider, n + 1);
      out.push(m.ref);
    }
  }
  return out.slice(0, max);
}
