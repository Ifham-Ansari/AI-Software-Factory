import { useNeedsYou } from "../screens/NeedsYou";
import { useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { useLive, useEvents } from "../lib/live";
import { useAction, useProject } from "../lib/queries";
import { href } from "../lib/router";
import { useTheme, type ThemePref } from "../lib/theme";
import { PHASE_LABELS, PHASES, type Phase, type ProjectInfo } from "../lib/types";
import { CountBadge, Icon, Modal, toast, toastError } from "./ui";
import { RequestChangeButton } from "./Changes";
import { Bell, NotificationToasts } from "./Notifications";
import { Logo } from "./Logo";

export const SCREENS: { id: string; label: string; icon: string; group: string }[] = [
  { id: "needs", label: "Needs you", icon: "inbox", group: "You" },
  { id: "idea", label: "Idea", icon: "idea", group: "You" },
  { id: "questions", label: "Questions", icon: "questions", group: "You" },
  { id: "docs", label: "Documents", icon: "docs", group: "Plan" },
  { id: "design", label: "Design", icon: "design", group: "Plan" },
  { id: "team", label: "Team builder", icon: "team", group: "Plan" },
  { id: "board", label: "Live board", icon: "board", group: "Build" },
  { id: "agents", label: "Agents", icon: "agents", group: "Build" },
  { id: "feed", label: "Team feed", icon: "feed", group: "Build" },
  { id: "preview", label: "Preview", icon: "preview", group: "Build" },
  { id: "memory", label: "Memory", icon: "memory", group: "Project" },
  { id: "usage", label: "Usage", icon: "usage", group: "Project" },
  { id: "keys", label: "API keys", icon: "key", group: "Project" },
  { id: "settings", label: "Settings", icon: "settings", group: "Project" },
];
const GROUPS = ["You", "Plan", "Build", "Project"];

/** Where to land when a project is opened without a screen. */
export function defaultScreen(p: ProjectInfo | undefined): string {
  if (!p) return "board";
  if (p.openQuestions > 0) return "questions";
  const m: Record<Phase, string> = {
    idea: "idea",
    discovery: "feed",
    prd_review: "docs/prd",
    design_direction: "design",
    design: "design",
    architecture_review: "docs/architecture",
    plan_review: "team",
    build: "board",
    release_review: "docs/release",
    done: "board",
  };
  return m[p.phase] ?? "board";
}

export function Shell({ pid, screen, children }: { pid: string; screen: string; children: ReactNode }) {
  const qc = useQueryClient();
  useLive(pid, qc);
  const project = useProject(pid);
  const p = project.data;
  const alerts = p?.state.alerts?.length ?? 0;
  const needs = useNeedsYou(pid).data?.length ?? 0;

  return (
    <div className="grid h-full grid-cols-[240px_minmax(0,1fr)] grid-rows-[auto_minmax(0,1fr)] bg-chrome max-[1100px]:grid-cols-[64px_minmax(0,1fr)]">
      <nav aria-label="Screens" className="row-span-2 flex min-h-0 flex-col max-[1100px]:items-center">
        <a
          href="#/"
          className="flex h-16 shrink-0 items-center gap-2.5 px-5 max-[1100px]:justify-center max-[1100px]:px-0"
          aria-label="AI Software Factory home"
        >
          <Logo size={30} />
          <span className="text-[14.5px] leading-tight font-bold tracking-[-0.025em] whitespace-nowrap max-[1100px]:sr-only">
            <span className="text-brand">AI</span> Software Factory
          </span>
        </a>
        <div className="flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto px-3 pb-3 max-[1100px]:px-2">
          <a
            href="#/"
            title="All projects"
            className="group mb-1 flex items-center gap-2.5 rounded-lg border border-rule bg-surface/60 px-2.5 py-1.75 text-[12.5px] font-medium text-ink-2 transition-colors hover:border-rule-strong hover:bg-surface hover:text-ink max-[1100px]:justify-center max-[1100px]:px-0 max-[1100px]:py-2"
          >
            <Icon name="folder" size={15} className="text-ink-3 transition-colors group-hover:text-accent" />
            <span className="flex-1 max-[1100px]:sr-only">All projects</span>
            <Icon name="chevron" size={13} className="text-ink-3 max-[1100px]:hidden" />
          </a>
          {GROUPS.map((g) => (
            <div key={g} className="flex flex-col gap-0.5">
              <div className="mono px-2.5 pt-4 pb-1.5 text-[10px] font-medium tracking-[0.16em] text-ink-3 uppercase max-[1100px]:hidden">
                {g}
              </div>
              <div className="hidden h-px bg-rule-strong max-[1100px]:my-2 max-[1100px]:block" aria-hidden />
              {SCREENS.filter((s) => s.group === g).map((s) => {
                const active = screen === s.id;
                const badge =
                  s.id === "needs"
                    ? needs
                    : s.id === "questions"
                      ? (p?.openQuestions ?? 0) + alerts
                      : s.id === "agents"
                        ? (p?.activeRuns ?? 0)
                        : 0;
                return (
                  <a
                    key={s.id}
                    href={href(pid, s.id)}
                    aria-current={active ? "page" : undefined}
                    title={s.label}
                    className={`group relative flex items-center gap-2.5 rounded-lg px-2.5 py-1.75 text-[13.5px] transition-[background-color,color,box-shadow] duration-150 max-[1100px]:justify-center max-[1100px]:px-0 max-[1100px]:py-2 ${active ? "bg-surface font-semibold text-ink shadow-(--shadow-sm) ring-1 ring-rule" : "text-ink-2 hover:bg-surface/60 hover:text-ink"}`}
                  >
                    {active && (
                      <span
                        aria-hidden
                        className="bg-brand absolute top-1/2 left-0 h-4 w-0.75 -translate-y-1/2 rounded-r-full"
                      />
                    )}
                    <Icon
                      name={s.icon}
                      size={17}
                      className={
                        active ? "text-accent" : "text-ink-3 transition-colors group-hover:text-ink-2"
                      }
                    />
                    <span className="flex-1 max-[1100px]:sr-only">{s.label}</span>
                    {badge > 0 && (
                      <span className="max-[1100px]:absolute max-[1100px]:-top-1 max-[1100px]:-right-1">
                        <CountBadge
                          n={badge}
                          tone={s.id === "questions" || s.id === "needs" ? "danger" : "accent"}
                          label={
                            s.id === "questions" || s.id === "needs"
                              ? `${badge} need you`
                              : `${badge} running`
                          }
                        />
                      </span>
                    )}
                  </a>
                );
              })}
            </div>
          ))}
        </div>
        <div className="mx-3 mb-3 flex shrink-0 flex-col gap-2.5 rounded-xl border border-rule bg-surface/60 px-3 py-2.5 max-[1100px]:mx-2 max-[1100px]:items-center max-[1100px]:px-1.5">
          <LiveStatus pid={pid} />
          <ThemeToggle />
        </div>
      </nav>
      <Header pid={pid} p={p} />
      <NotificationToasts pid={pid} />
      <main
        id="main"
        tabIndex={-1}
        className="canvas col-start-2 row-start-2 mr-2 mb-2 min-h-0 overflow-y-auto rounded-b-[14px] border border-t-0 border-rule shadow-(--shadow-sm) outline-none max-[1100px]:mr-1.5 max-[1100px]:mb-1.5"
      >
        {children}
      </main>
    </div>
  );
}

function LiveStatus({ pid }: { pid: string }) {
  const { status } = useEvents(pid);
  const label = status === "live" ? "live" : status === "connecting" ? "connecting" : "offline, retrying";
  const color = status === "live" ? "var(--ok)" : status === "connecting" ? "var(--warn)" : "var(--danger)";
  return (
    <div
      className="mono flex items-center gap-2 text-[11px] font-medium tracking-wide text-ink-3"
      role="status"
      aria-label={`Live updates ${label}`}
    >
      <span className="relative flex h-2 w-2">
        {status === "live" && (
          <span
            className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-60"
            style={{ background: color }}
          />
        )}
        <span className="relative inline-flex h-2 w-2 rounded-full" style={{ background: color }} />
      </span>
      <span className="max-[1100px]:sr-only">{label}</span>
    </div>
  );
}

function Header({ pid, p }: { pid: string; p: ProjectInfo | undefined }) {
  const [killOpen, setKillOpen] = useState(false);
  const pause = useAction(pid, "POST", "/control/pause");
  const resume = useAction(pid, "POST", "/control/resume");
  const kill = useAction<unknown, { killed: number }>(pid, "POST", "/control/kill", [
    "project",
    "agents",
    "tasks",
  ]);
  const paused = Boolean(p?.state.paused);

  return (
    <header className="col-start-2 row-start-1 mt-2 mr-2 rounded-t-[14px] border border-rule bg-surface shadow-(--shadow-sm) max-[1100px]:mt-1.5 max-[1100px]:mr-1.5">
      <div className="flex h-14 items-center gap-3 px-5">
        <span
          aria-hidden
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] bg-accent-soft text-accent ring-1 ring-[color-mix(in_srgb,var(--accent)_22%,transparent)]"
        >
          <Icon name="folder" size={17} />
        </span>
        <div className="min-w-0">
          <div className="mono text-[10px] leading-none font-medium tracking-[0.16em] text-ink-3 uppercase">
            Project
          </div>
          <div
            className="mt-0.5 truncate text-[16px] leading-tight font-bold tracking-[-0.02em]"
            data-testid="project-name"
            title={p?.root}
          >
            {p?.name ?? "…"}
          </div>
        </div>
        {p?.state.paused && (
          <span
            className="mono inline-flex items-center gap-1.5 rounded-full border border-[color-mix(in_srgb,var(--warn)_45%,transparent)] bg-warn-soft px-2.5 text-[11px] leading-5.5 text-warn"
            role="status"
          >
            <span aria-hidden className="pulse-dot h-1.5 w-1.5 rounded-full bg-warn" />
            paused{p.state.pauseReason ? `: ${p.state.pauseReason}` : ""}
          </span>
        )}
        <div className="ml-auto flex items-center gap-2">
          <RequestChangeButton pid={pid} p={p} />
          <Bell pid={pid} />
          <a
            href={href(pid, "questions")}
            className="btn btn-sm"
            aria-label={`${p?.openQuestions ?? 0} open questions`}
            data-testid="questions-badge"
          >
            <Icon name="questions" size={14} />
            <span className="max-[1280px]:hidden">Questions</span>
            <span
              className={`mono rounded-full px-1.5 text-[11px] leading-4 font-semibold ${p?.openQuestions ? "bg-danger text-danger-ink" : "bg-sunken text-ink-3"}`}
            >
              {p?.openQuestions ?? 0}
            </span>
          </a>
          {paused ? (
            <button
              className="btn btn-sm"
              onClick={() =>
                resume.mutate(undefined, { onSuccess: () => toast("Scheduler resumed"), onError: toastError })
              }
              disabled={resume.isPending}
            >
              <Icon name="play" size={13} /> Resume
            </button>
          ) : (
            <button
              className="btn btn-sm"
              onClick={() =>
                pause.mutate(undefined, {
                  onSuccess: () => toast("Scheduler paused. Running agents finish their current run."),
                  onError: toastError,
                })
              }
              disabled={pause.isPending || !p}
            >
              <Icon name="pause" size={13} /> Pause
            </button>
          )}
          <button
            className="btn btn-sm btn-danger"
            onClick={() => setKillOpen(true)}
            disabled={!p}
            data-testid="kill-switch"
          >
            <Icon name="power" size={13} /> Kill switch
          </button>
        </div>
      </div>
      <PhaseStepper phase={p?.phase} />
      <Modal
        open={killOpen}
        onClose={() => setKillOpen(false)}
        title="Stop every agent now?"
        footer={
          <>
            <button className="btn" onClick={() => setKillOpen(false)} autoFocus>
              Cancel
            </button>
            <button
              className="btn btn-danger"
              disabled={kill.isPending}
              onClick={() =>
                kill.mutate(undefined, {
                  onSuccess: (r) => {
                    setKillOpen(false);
                    toast(
                      `Kill switch: stopped ${r.killed} agent run${r.killed === 1 ? "" : "s"}. AI Software Factory is paused.`,
                    );
                  },
                  onError: toastError,
                })
              }
            >
              {kill.isPending ? "Stopping…" : "Stop all agents"}
            </button>
          </>
        }
      >
        <p>
          Every running Claude Code process is killed immediately and the scheduler is paused. Work in
          progress stays in each task's worktree; when you resume, agents pick up from where they stopped.
        </p>
        <p className="mt-2 text-ink-3">Use Pause instead if you only want to stop new runs from starting.</p>
      </Modal>
    </header>
  );
}

function PhaseStepper({ phase }: { phase: Phase | undefined }) {
  const cur = phase ? PHASES.indexOf(phase) : -1;
  return (
    <ol
      aria-label="Project phase"
      className="flex gap-1.5 overflow-x-auto px-5 pt-0.5 pb-3"
      data-testid="phase-stepper"
    >
      {PHASES.map((ph, i) => {
        const state = i < cur ? "past" : i === cur ? "current" : "future";
        return (
          <li
            key={ph}
            aria-current={state === "current" ? "step" : undefined}
            className="flex min-w-fit flex-1 basis-0 flex-col gap-1.5"
          >
            <span
              aria-hidden
              className={`h-1 w-full rounded-full ${state === "current" ? "phase-live" : state === "past" ? "bg-brand" : "bg-rule"}`}
            />
            <div
              className={`flex items-center gap-1.5 pr-1 text-[11.5px] whitespace-nowrap transition-colors ${state === "current" ? "font-semibold text-ink" : state === "past" ? "font-medium text-ink-2" : "text-ink-3"}`}
            >
              <span
                aria-hidden
                className={`mono flex h-4 w-4 items-center justify-center rounded-[5px] text-[9.5px] font-semibold ${state === "current" ? "bg-brand text-brand-ink shadow-[0_0_0_3px_color-mix(in_srgb,var(--accent)_18%,transparent)]" : state === "past" ? "bg-accent-soft text-accent" : "border border-rule-strong text-ink-3"}`}
              >
                {state === "past" ? <Icon name="check" size={10} /> : i}
              </span>
              <span>{PHASE_LABELS[ph]}</span>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function ThemeToggle() {
  const { pref, setPref } = useTheme();
  const opts: { id: ThemePref; icon: string; label: string }[] = [
    { id: "system", icon: "system", label: "System theme" },
    { id: "light", icon: "sun", label: "Light theme" },
    { id: "dark", icon: "moon", label: "Dark theme" },
  ];
  return (
    <div
      role="group"
      aria-label="Theme"
      className="flex w-fit gap-0.5 rounded-lg bg-sunken p-0.5 ring-1 ring-rule max-[1100px]:flex-col"
      data-testid="theme-toggle"
    >
      {opts.map((o) => (
        <button
          key={o.id}
          aria-pressed={pref === o.id}
          aria-label={o.label}
          title={o.label}
          onClick={() => setPref(o.id)}
          className={`flex h-6.5 w-8 items-center justify-center rounded-md transition-colors ${pref === o.id ? "bg-surface text-accent shadow-(--shadow-sm) ring-1 ring-rule" : "text-ink-3 hover:text-ink"}`}
        >
          <Icon name={o.icon} size={14} />
        </button>
      ))}
    </div>
  );
}
