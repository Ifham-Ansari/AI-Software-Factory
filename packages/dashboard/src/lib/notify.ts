import { useSyncExternalStore } from "react";
import type { AsfEvent, Notify } from "./types";

// Owner notifications: events that carry data.notify (see notificationFor in packages/server/src/service.ts).
// Past ones come from GET /notifications; only live WebSocket ones raise toasts and desktop notifications.

export type NoteEvent = AsfEvent & { data: AsfEvent["data"] & { notify: Notify } };

export interface Toast {
  key: number;
  ev: NoteEvent;
}

const MAX_TOASTS = 4;
const TOAST_MS: Record<Notify["level"], number | null> = {
  info: 6000,
  success: 6000,
  warning: 10_000,
  action: null,
};

function lsGet(k: string): string | null {
  try {
    return localStorage.getItem(k);
  } catch {
    return null;
  }
}
function lsSet(k: string, v: string): void {
  try {
    localStorage.setItem(k, v);
  } catch {
    /* private mode */
  }
}

export function isNote(e: AsfEvent): e is NoteEvent {
  const n = (e.data as { notify?: unknown } | undefined)?.notify;
  return Boolean(n && typeof n === "object" && "title" in (n as object));
}

export const prefs = {
  desktop: () => lsGet("asf.notify.desktop") === "1",
  setDesktop: (on: boolean) => lsSet("asf.notify.desktop", on ? "1" : "0"),
  sound: () => lsGet("asf.notify.sound") === "1",
  setSound: (on: boolean) => lsSet("asf.notify.sound", on ? "1" : "0"),
};

function beep(): void {
  try {
    const Ctx =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    const o = ctx.createOscillator();
    const g = ctx.createGain();
    o.type = "sine";
    o.frequency.value = 880;
    g.gain.setValueAtTime(0.0001, ctx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.15, ctx.currentTime + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.25);
    o.connect(g).connect(ctx.destination);
    o.start();
    o.stop(ctx.currentTime + 0.3);
    o.onended = () => void ctx.close();
  } catch {
    /* no audio */
  }
}

/** What decides whether a notification is unread: everything up to "mark all read", plus the ones opened since. */
export interface ReadState {
  lastSeen: number;
  read: ReadonlySet<number>;
}

export function isUnread(s: ReadState, ev: { id: number }): boolean {
  return ev.id > s.lastSeen && !s.read.has(ev.id);
}

/** The screen a notification belongs to (and opens). */
export function noteScreen(n: Notify): string {
  return n.screen || "questions";
}

const LEVEL_RANK: Record<Notify["level"], number> = { action: 3, warning: 2, success: 1, info: 0 };

/** Unread notifications per screen, with the most important level among them (for the nav highlights). */
export function unreadByScreen(s: ReadState & { notes: NoteEvent[] }): Map<string, { count: number; level: Notify["level"] }> {
  const out = new Map<string, { count: number; level: Notify["level"] }>();
  for (const ev of s.notes) {
    if (!isUnread(s, ev)) continue;
    const n = ev.data.notify;
    const cur = out.get(noteScreen(n));
    if (!cur) out.set(noteScreen(n), { count: 1, level: n.level });
    else {
      cur.count++;
      if (LEVEL_RANK[n.level] > LEVEL_RANK[cur.level]) cur.level = n.level;
    }
  }
  return out;
}

export class NoteStore {
  readonly pid: string;
  notes: NoteEvent[] = [];
  toasts: Toast[] = [];
  lastSeen: number;
  /** Notifications read one at a time (opened, or their screen visited) after `lastSeen`. */
  read: Set<number>;
  private toastKey = 0;
  private listeners = new Set<() => void>();
  private snap: { notes: NoteEvent[]; toasts: Toast[]; lastSeen: number; read: ReadonlySet<number> };

  constructor(pid: string) {
    this.pid = pid;
    this.lastSeen = Number(lsGet(`asf.notify.seen.${pid}`) ?? 0) || 0;
    this.read = new Set(readIds(lsGet(`asf.notify.read.${pid}`)).filter((id) => id > this.lastSeen));
    this.snap = { notes: this.notes, toasts: this.toasts, lastSeen: this.lastSeen, read: this.read };
  }

  subscribe = (l: () => void) => {
    this.listeners.add(l);
    return () => this.listeners.delete(l);
  };
  snapshot = () => this.snap;
  private emit() {
    this.snap = { notes: this.notes, toasts: this.toasts, lastSeen: this.lastSeen, read: this.read };
    for (const l of this.listeners) l();
  }

  /** Mark these notifications read (one was opened). */
  markRead(ids: number[]): void {
    const add = ids.filter((id) => isUnread(this, { id }));
    if (!add.length) return;
    // A new set, so React sees the change; ids at or below lastSeen are read anyway.
    this.read = new Set([...[...this.read].filter((id) => id > this.lastSeen).slice(-500), ...add]);
    lsSet(`asf.notify.read.${this.pid}`, JSON.stringify([...this.read]));
    this.emit();
  }

  /** The owner is looking at this screen: its notifications are read. */
  markScreenRead(screen: string): void {
    this.markRead(this.notes.filter((n) => noteScreen(n.data.notify) === screen).map((n) => n.id));
  }

  /** Past notifications (HTTP backfill): listed in the bell, never toasted. */
  backfill(evs: AsfEvent[]): void {
    const known = new Set(this.notes.map((n) => n.id));
    const add = evs.filter((e) => isNote(e) && !known.has(e.id)) as NoteEvent[];
    if (!add.length) return;
    this.notes = [...this.notes, ...add].sort((a, b) => a.id - b.id).slice(-500);
    this.emit();
  }

  /** Live events from the WebSocket: list + toast + desktop notification. */
  live(evs: AsfEvent[]): void {
    const known = new Set(this.notes.map((n) => n.id));
    const add = evs.filter((e) => isNote(e) && !known.has(e.id)) as NoteEvent[];
    if (!add.length) return;
    this.notes = [...this.notes, ...add].sort((a, b) => a.id - b.id).slice(-500);
    for (const ev of add) {
      const key = ++this.toastKey;
      this.toasts = [...this.toasts, { key, ev }].slice(-MAX_TOASTS);
      const ms = TOAST_MS[ev.data.notify.level];
      if (ms) setTimeout(() => this.dismiss(key), ms);
      this.desktop(ev);
    }
    this.emit();
  }

  private desktop(ev: NoteEvent): void {
    const n = ev.data.notify;
    if (n.level === "action" && prefs.sound()) beep();
    if (n.level === "info" || !prefs.desktop() || typeof Notification === "undefined") return;
    if (Notification.permission !== "granted" || document.visibilityState !== "hidden") return;
    try {
      const d = new Notification(n.title, { body: n.body ?? "", tag: String(ev.id) });
      d.onclick = () => {
        window.focus();
        window.location.hash = targetHash(this.pid, n);
        d.close();
      };
    } catch {
      /* not supported */
    }
  }

  dismiss(key: number): void {
    const before = this.toasts.length;
    this.toasts = this.toasts.filter((t) => t.key !== key);
    if (this.toasts.length !== before) this.emit();
  }

  markAllRead(): void {
    const max = this.notes.at(-1)?.id ?? this.lastSeen;
    if (max === this.lastSeen) return;
    this.lastSeen = max;
    this.read = new Set();
    lsSet(`asf.notify.seen.${this.pid}`, String(max));
    lsSet(`asf.notify.read.${this.pid}`, "[]");
    this.emit();
  }
}

function readIds(raw: string | null): number[] {
  try {
    const v: unknown = JSON.parse(raw ?? "[]");
    return Array.isArray(v) ? v.filter((x): x is number => Number.isInteger(x)) : [];
  } catch {
    return [];
  }
}

const stores = new Map<string, NoteStore>();
export function noteStore(pid: string): NoteStore {
  let s = stores.get(pid);
  if (!s) {
    s = new NoteStore(pid);
    stores.set(pid, s);
  }
  return s;
}

export function useNotes(pid: string) {
  const s = noteStore(pid);
  return useSyncExternalStore(s.subscribe, s.snapshot, s.snapshot);
}

/** Where clicking a notification goes. */
export function targetHash(pid: string, n: Notify): string {
  const p = `#/p/${encodeURIComponent(pid)}`;
  if (n.screen === "board") return n.task ? `${p}/board/${encodeURIComponent(n.task)}` : `${p}/board`;
  if (n.screen === "docs")
    return n.doc ? `${p}/docs/${n.doc.split("/").map(encodeURIComponent).join("/")}` : `${p}/docs`;
  return `${p}/${n.screen || "questions"}`;
}
