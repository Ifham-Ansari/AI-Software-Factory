import { describe, expect, it } from "vitest";
import { isUnread, NoteStore, unreadByScreen, type NoteEvent } from "./notify";
import type { Notify } from "./types";

const note = (id: number, screen: string, level: Notify["level"] = "info"): NoteEvent => ({
  id,
  ts: "2026-11-22T10:00:00Z",
  type: "test",
  actor: null,
  role: null,
  task: null,
  run_id: null,
  summary: "",
  data: { notify: { level, title: `note ${id}`, screen } },
});

describe("notification read state", () => {
  it("opening a notification, or the screen it belongs to, marks it read; the tab highlights follow", () => {
    const s = new NoteStore("read-state");
    s.backfill([note(1, "board", "success"), note(2, "questions", "action"), note(3, "board", "warning"), note(4, "agents")]);
    // Each tab shows its unread count and the most important level among them.
    expect(unreadByScreen(s.snapshot())).toEqual(
      new Map([
        ["board", { count: 2, level: "warning" }],
        ["questions", { count: 1, level: "action" }],
        ["agents", { count: 1, level: "info" }],
      ]),
    );
    s.markRead([2]);
    expect(isUnread(s.snapshot(), { id: 2 })).toBe(false);
    expect(isUnread(s.snapshot(), { id: 1 })).toBe(true);
    s.markScreenRead("board");
    expect([...unreadByScreen(s.snapshot()).keys()]).toEqual(["agents"]);
    s.markAllRead();
    expect(unreadByScreen(s.snapshot()).size).toBe(0);
    // Later notifications are unread again.
    s.backfill([note(5, "docs", "action")]);
    expect(unreadByScreen(s.snapshot()).get("docs")).toEqual({ count: 1, level: "action" });
  });

  it("a notification without a screen belongs to Questions", () => {
    const s = new NoteStore("no-screen");
    s.backfill([note(1, "")]);
    expect([...unreadByScreen(s.snapshot()).keys()]).toEqual(["questions"]);
    s.markScreenRead("questions");
    expect(unreadByScreen(s.snapshot()).size).toBe(0);
  });
});
