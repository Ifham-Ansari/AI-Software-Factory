import type { Settings } from "./config.ts";

export interface QuotaState {
  usedToday: number;
  /** Epoch ms until which Claude Code reported a usage limit. */
  limitedUntil?: number | null;
}

export interface QuotaDecision {
  ok: boolean;
  reason?: string;
  allowance: number;
}

/** AI Software Factory may start runs while today's budget tokens stay under (100 - reserve)% of the daily budget. */
export function quotaCheck(settings: Settings, state: QuotaState, now = Date.now()): QuotaDecision {
  const allowance = settings.daily_token_budget > 0 ? Math.floor((settings.daily_token_budget * (100 - settings.reserve_percent)) / 100) : Infinity;
  if (state.limitedUntil && state.limitedUntil > now) {
    return { ok: false, reason: `usage limit reached; resumes at ${new Date(state.limitedUntil).toISOString()}`, allowance };
  }
  if (state.usedToday >= allowance) {
    return { ok: false, reason: `daily budget reached (${state.usedToday} of ${allowance} tokens AI Software Factory may use)`, allowance };
  }
  return { ok: true, allowance };
}

/** Default tokens per run by role, used for estimates before there is history. */
export const DEFAULT_RUN_TOKENS: Record<string, number> = {
  pm: 120_000,
  "tech-lead": 250_000,
  designer: 180_000,
  backend: 220_000,
  frontend: 220_000,
  qa: 160_000,
  reviewer: 90_000,
  devops: 150_000,
  security: 150_000,
};

/** Default turns per run by role. With the built-in engine every turn is one API request, and free tiers limit requests per day. */
export const DEFAULT_RUN_TURNS: Record<string, number> = {
  pm: 15,
  "tech-lead": 30,
  designer: 25,
  backend: 30,
  frontend: 30,
  qa: 20,
  reviewer: 12,
  devops: 20,
  security: 20,
};

export interface Estimate {
  byRole: Record<string, { tasks: number; perRun: number; tokens: number; requests: number }>;
  totalTokens: number;
  /** API requests (turns), the limit that matters most on free tiers. */
  totalRequests: number;
}

/** Estimate = task count by role x average run cost by role (history first, defaults otherwise), plus review and QA runs per task. */
export function estimateBuild(tasksByRole: Record<string, number>, avgByRole: Record<string, number>, qaPerTask = true, avgTurnsByRole: Record<string, number> = {}): Estimate {
  const per = (r: string) => avgByRole[r] ?? DEFAULT_RUN_TOKENS[r] ?? 150_000;
  const turns = (r: string) => avgTurnsByRole[r] ?? DEFAULT_RUN_TURNS[r] ?? 20;
  const byRole: Estimate["byRole"] = {};
  const add = (role: string, tasks: number) => {
    const cur = byRole[role] ?? { tasks: 0, perRun: per(role), tokens: 0, requests: 0 };
    cur.tasks += tasks;
    cur.tokens = cur.tasks * cur.perRun;
    cur.requests = Math.round(cur.tasks * turns(role));
    byRole[role] = cur;
  };
  let n = 0;
  for (const [role, count] of Object.entries(tasksByRole)) {
    add(role, count);
    n += count;
  }
  add("reviewer", n);
  if (qaPerTask) add("qa", n);
  const totalTokens = Object.values(byRole).reduce((a, b) => a + b.tokens, 0);
  const totalRequests = Object.values(byRole).reduce((a, b) => a + b.requests, 0);
  return { byRole, totalTokens, totalRequests };
}
