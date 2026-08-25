import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { EventResponse } from "@factory/contracts";
import { RunEventStream, type ConnectionStatus } from "@/lib/ws/stream";

/**
 * Realtime client [F-215].
 *
 * The stream is tested directly rather than through a component: its whole job is
 * sequencing and reconnection, and a renderer adds nothing but noise. A fake WebSocket
 * and a stubbed `fetch` make the interesting cases — a gap after a drop, a duplicate
 * arriving mid-replay — reproducible instead of timing-dependent.
 */

const RUN_ID = "11111111-1111-4111-8111-111111111111";

function makeEvent(seq: number): EventResponse {
  return {
    event_id: `event-${seq}`,
    seq,
    type: "run.log",
    run_id: RUN_ID,
    project_id: "22222222-2222-4222-8222-222222222222",
    occurred_at: "2026-08-24T12:00:00Z",
    actor_kind: "system",
    actor_id: null,
    payload: { kind: "log", message: `line ${seq}`, level: "info" },
  } as unknown as EventResponse;
}

/** A WebSocket stand-in whose lifecycle the test drives explicitly. */
class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;

  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }

  close(): void {
    this.closed = true;
  }

  /** Simulate the server pushing an event. */
  deliver(event: EventResponse): void {
    this.onmessage?.({ data: JSON.stringify(event) } as MessageEvent<string>);
  }
}

/** Stub `fetch` so replay returns a scripted set of pages. */
function stubFetch(pagesBySeq: Record<number, EventResponse[]>): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init?: RequestInit) => {
      if (input.includes("ws-ticket") || init?.method === "POST") {
        return {
          ok: true,
          json: async () => ({ socket_url: "ws://test/ws/runs/x?ticket=t" }),
        } as Response;
      }
      const after = Number(new URL(input, "http://test").searchParams.get("after_seq"));
      const items = pagesBySeq[after] ?? [];
      return {
        ok: true,
        json: async () => ({ items, has_more: false, next_seq: 0, latest_seq: 0 }),
      } as Response;
    }),
  );
}

describe("RunEventStream", () => {
  beforeEach(() => {
    FakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeWebSocket);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("replays missed events before opening the socket", async () => {
    stubFetch({ 0: [makeEvent(1), makeEvent(2)] });
    const seen: number[] = [];
    const stream = new RunEventStream(RUN_ID, {
      onEvent: (event) => seen.push(event.seq),
      onStatus: () => undefined,
    });

    await stream.start();

    expect(seen).toEqual([1, 2]);
    expect(stream.cursor).toBe(2);
    stream.close();
  });

  it("reports live once the socket opens", async () => {
    stubFetch({ 0: [] });
    const statuses: ConnectionStatus[] = [];
    const stream = new RunEventStream(RUN_ID, {
      onEvent: () => undefined,
      onStatus: (status) => statuses.push(status),
    });

    await stream.start();
    FakeWebSocket.instances[0]?.onopen?.();

    expect(statuses).toContain("connecting");
    expect(statuses.at(-1)).toBe("live");
    stream.close();
  });

  it("delivers events arriving over the socket", async () => {
    stubFetch({ 0: [] });
    const seen: number[] = [];
    const stream = new RunEventStream(RUN_ID, {
      onEvent: (event) => seen.push(event.seq),
      onStatus: () => undefined,
    });
    await stream.start();

    FakeWebSocket.instances[0]?.deliver(makeEvent(1));
    FakeWebSocket.instances[0]?.deliver(makeEvent(2));

    expect(seen).toEqual([1, 2]);
    stream.close();
  });

  it("discards an event it has already seen", async () => {
    // The race the "replay first, then socket" ordering can produce: an event arrives on
    // the socket while the replay covering it is still in flight.
    stubFetch({ 0: [makeEvent(1), makeEvent(2)] });
    const seen: number[] = [];
    const stream = new RunEventStream(RUN_ID, {
      onEvent: (event) => seen.push(event.seq),
      onStatus: () => undefined,
    });
    await stream.start();

    FakeWebSocket.instances[0]?.deliver(makeEvent(2));
    FakeWebSocket.instances[0]?.deliver(makeEvent(3));

    expect(seen).toEqual([1, 2, 3]);
    stream.close();
  });

  it("ignores a frame that will not parse", async () => {
    stubFetch({ 0: [] });
    const seen: number[] = [];
    const stream = new RunEventStream(RUN_ID, {
      onEvent: (event) => seen.push(event.seq),
      onStatus: () => undefined,
    });
    await stream.start();

    FakeWebSocket.instances[0]?.onmessage?.({ data: "not json" } as MessageEvent<string>);

    expect(seen).toEqual([]);
    stream.close();
  });

  it("closing prevents any reconnection", async () => {
    stubFetch({ 0: [] });
    const statuses: ConnectionStatus[] = [];
    const stream = new RunEventStream(RUN_ID, {
      onEvent: () => undefined,
      onStatus: (status) => statuses.push(status),
    });
    await stream.start();

    stream.close();
    // A close initiated by us must not schedule a retry.
    FakeWebSocket.instances[0]?.onclose?.();

    expect(statuses.at(-1)).toBe("idle");
  });

  it("polls for events the socket did not deliver", async () => {
    // The Redis-down case. Fan-out is unavailable, so the socket stays open and silent;
    // without the poll a connected client would look healthy while receiving nothing.
    vi.useFakeTimers();
    try {
      const pages: Record<number, EventResponse[]> = { 0: [] };
      stubFetch(pages);
      const seen: number[] = [];
      const stream = new RunEventStream(RUN_ID, {
        onEvent: (event) => seen.push(event.seq),
        onStatus: () => undefined,
      });
      await stream.start();
      FakeWebSocket.instances[0]?.onopen?.();
      expect(seen).toEqual([]);

      // An event lands in the database but is never published.
      pages[0] = [makeEvent(1)];

      await vi.advanceTimersByTimeAsync(5_000);

      expect(seen).toEqual([1]);
      stream.close();
    } finally {
      vi.useRealTimers();
    }
  });

  it("stops polling once closed", async () => {
    vi.useFakeTimers();
    try {
      const pages: Record<number, EventResponse[]> = { 0: [] };
      stubFetch(pages);
      const seen: number[] = [];
      const stream = new RunEventStream(RUN_ID, {
        onEvent: (event) => seen.push(event.seq),
        onStatus: () => undefined,
      });
      await stream.start();
      stream.close();

      pages[0] = [makeEvent(1)];
      await vi.advanceTimersByTimeAsync(20_000);

      expect(seen).toEqual([]);
    } finally {
      vi.useRealTimers();
    }
  });

  it("keeps its cursor so a reconnect asks only for the gap", async () => {
    stubFetch({ 0: [makeEvent(1), makeEvent(2)] });
    const stream = new RunEventStream(RUN_ID, {
      onEvent: () => undefined,
      onStatus: () => undefined,
    });
    await stream.start();

    FakeWebSocket.instances[0]?.deliver(makeEvent(3));

    // The next replay would request after_seq=3, which is what makes reconnection
    // lossless and duplicate-free.
    expect(stream.cursor).toBe(3);
    stream.close();
  });
});
