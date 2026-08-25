/**
 * The realtime event stream: replay, then socket, then replay again on reconnect.
 *
 * The contract that makes reconnection lossless is the sequence cursor. Every event
 * carries a `seq` that is dense within its run, so the client can always say "I have
 * everything up to N" and be given exactly the gap.
 *
 * The connect sequence is therefore:
 *
 * 1. **Replay** over REST from the last `seq` seen (0 on a first connection).
 * 2. **Open the socket**, which delivers everything from now on.
 * 3. On drop, **go back to step 1**. Anything that happened during the outage arrives in
 *    the replay; anything after it arrives on the new socket.
 *
 * Step 1 before step 2 can duplicate an event that arrives on the socket while the replay
 * is in flight. That is handled by discarding any event whose `seq` is not greater than
 * the highest already seen — cheap, and far safer than the alternative ordering, which
 * would leave a genuine hole.
 *
 * **A slow poll runs alongside the socket.** The socket depends on Redis fan-out, and Redis
 * is explicitly allowed to be absent or down — in which case events are still written to
 * Postgres and the socket simply goes quiet. Without a poll a connected client would look
 * healthy while silently receiving nothing. The poll makes delivery degrade to a few
 * seconds of latency rather than stopping, and costs one cheap request per interval
 * because a caught-up replay returns an empty page.
 */

import type { EventResponse } from "@factory/contracts";

/** What the stream is currently doing, for the connection indicator. */
export type ConnectionStatus =
  | "idle"
  | "connecting"
  | "live"
  | "reconnecting"
  | "offline";

export interface StreamHandlers {
  onEvent: (event: EventResponse) => void;
  onStatus: (status: ConnectionStatus) => void;
}

/** Backoff schedule for reconnection, in milliseconds. */
const RETRY_DELAYS_MS = [500, 1_000, 2_000, 5_000, 10_000] as const;

/** Give up announcing "reconnecting" after this many failures and report offline. */
const MAX_ATTEMPTS_BEFORE_OFFLINE = RETRY_DELAYS_MS.length;

/**
 * How often to replay as a safety net while connected.
 *
 * Bounds delivery latency when fan-out is unavailable — Redis down, or a publish lost.
 * Slow enough that it costs almost nothing when the socket is doing its job, since a
 * caught-up replay returns an empty page.
 */
const POLL_INTERVAL_MS = 5_000;

/**
 * A live view of one run's events.
 *
 * Not a React hook: keeping the socket lifecycle out of React means it survives a
 * re-render and can be tested without a renderer.
 */
export class RunEventStream {
  private readonly runId: string;
  private readonly handlers: StreamHandlers;
  private socket: WebSocket | null = null;
  private lastSeq = 0;
  private attempts = 0;
  private closed = false;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private pollTimer: ReturnType<typeof setInterval> | null = null;
  private replaying = false;

  constructor(runId: string, handlers: StreamHandlers) {
    this.runId = runId;
    this.handlers = handlers;
  }

  /** The highest sequence number processed so far. Exposed for tests and diagnostics. */
  get cursor(): number {
    return this.lastSeq;
  }

  /** Begin streaming. Safe to call once; use `close()` to stop. */
  async start(): Promise<void> {
    this.closed = false;
    this.startPolling();
    await this.connect();
  }

  /** Stop streaming and release the socket. Idempotent. */
  close(): void {
    this.closed = true;
    if (this.retryTimer !== null) {
      clearTimeout(this.retryTimer);
      this.retryTimer = null;
    }
    if (this.pollTimer !== null) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
    if (this.socket) {
      // Drop the handler first: closing fires `onclose`, which would otherwise schedule
      // a reconnect for a stream the caller has explicitly finished with.
      this.socket.onclose = null;
      this.socket.close();
      this.socket = null;
    }
    this.handlers.onStatus("idle");
  }

  private async connect(): Promise<void> {
    if (this.closed) return;
    this.handlers.onStatus(this.attempts === 0 ? "connecting" : "reconnecting");

    try {
      await this.replay();
      const url = await this.mintTicket();
      if (this.closed) return;
      this.openSocket(url);
    } catch {
      // Any failure in the connect sequence is the same event: we are not live. The
      // specific cause is not actionable by the user, and the retry is identical.
      this.scheduleRetry();
    }
  }

  /**
   * Poll for anything the socket did not deliver.
   *
   * Failures are swallowed: this is a safety net, and a transient failure will be retried
   * on the next tick. Surfacing it as a connection error would misreport a healthy socket
   * as broken.
   */
  private startPolling(): void {
    if (this.pollTimer !== null) return;
    this.pollTimer = setInterval(() => {
      if (this.closed) return;
      void this.replay().catch(() => undefined);
    }, POLL_INTERVAL_MS);
  }

  /** Fetch everything after the cursor, paging until caught up. */
  private async replay(): Promise<void> {
    // The poll and a reconnect can overlap. Both advance the same cursor, so letting them
    // run concurrently would issue duplicate requests for the same page.
    if (this.replaying) return;
    this.replaying = true;
    try {
      await this.replayPages();
    } finally {
      this.replaying = false;
    }
  }

  /** Page through the gap until caught up. */
  private async replayPages(): Promise<void> {
    for (;;) {
      const response = await fetch(
        `/api/runs/${encodeURIComponent(this.runId)}/events?after_seq=${this.lastSeq}`,
        { cache: "no-store" },
      );
      if (!response.ok) throw new Error(`replay failed: ${response.status}`);

      const page = (await response.json()) as {
        items: EventResponse[];
        has_more: boolean;
      };
      for (const event of page.items) this.accept(event);
      if (!page.has_more || page.items.length === 0) return;
    }
  }

  private async mintTicket(): Promise<string> {
    const response = await fetch(
      `/api/runs/${encodeURIComponent(this.runId)}/ws-ticket`,
      { method: "POST", cache: "no-store" },
    );
    if (!response.ok) throw new Error(`ticket failed: ${response.status}`);
    const body = (await response.json()) as { socket_url: string };
    return body.socket_url;
  }

  private openSocket(url: string): void {
    const socket = new WebSocket(url);
    this.socket = socket;

    socket.onopen = () => {
      this.attempts = 0;
      this.handlers.onStatus("live");
    };

    socket.onmessage = (message: MessageEvent<string>) => {
      try {
        this.accept(JSON.parse(message.data) as EventResponse);
      } catch {
        // A frame that will not parse is not worth tearing the socket down for; the
        // event is durable and the next replay will deliver it correctly.
      }
    };

    socket.onclose = () => {
      this.socket = null;
      this.scheduleRetry();
    };

    // `onerror` is always followed by `onclose`, so retrying here as well would double
    // the backoff schedule.
    socket.onerror = () => undefined;
  }

  /**
   * Deliver an event, discarding anything already seen.
   *
   * The deduplication that makes "replay first, then socket" safe.
   */
  private accept(event: EventResponse): void {
    if (event.seq <= this.lastSeq) return;
    this.lastSeq = event.seq;
    this.handlers.onEvent(event);
  }

  private scheduleRetry(): void {
    if (this.closed) return;
    const delay =
      RETRY_DELAYS_MS[Math.min(this.attempts, RETRY_DELAYS_MS.length - 1)] ?? 10_000;
    this.attempts += 1;
    this.handlers.onStatus(
      this.attempts > MAX_ATTEMPTS_BEFORE_OFFLINE ? "offline" : "reconnecting",
    );
    this.retryTimer = setTimeout(() => {
      this.retryTimer = null;
      void this.connect();
    }, delay);
  }
}
