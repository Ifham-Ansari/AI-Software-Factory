"use client";

import { useEffect, useRef, useState } from "react";
import type { EventResponse } from "@factory/contracts";
import { RunEventStream, type ConnectionStatus } from "@/lib/ws/stream";

/** How many events to keep in memory. A long run would otherwise grow without bound. */
const MAX_BUFFERED_EVENTS = 500;

export interface RunEventsState {
  events: EventResponse[];
  status: ConnectionStatus;
}

/**
 * Subscribe a component to a run's live event stream.
 *
 * The stream instance lives in a ref rather than state: it is a mutable resource with a
 * lifecycle, not a rendered value, and putting it in state would tear the socket down on
 * every re-render.
 *
 * Events accumulate in order and are capped — a run emitting thousands of lines should
 * cost bounded memory, and the full history is always available by replaying over REST.
 */
export function useRunEvents(runId: string | null): RunEventsState {
  const [events, setEvents] = useState<EventResponse[]>([]);
  const [streamStatus, setStreamStatus] = useState<ConnectionStatus>("idle");
  const streamRef = useRef<RunEventStream | null>(null);

  // Switching runs must not show the previous run's events. Adjusting state during
  // render rather than in an Effect is React's documented pattern for "reset when a prop
  // changes" — an Effect would render the stale list once before clearing it.
  const [seenRunId, setSeenRunId] = useState(runId);
  if (runId !== seenRunId) {
    setSeenRunId(runId);
    setEvents([]);
    setStreamStatus("idle");
  }

  useEffect(() => {
    if (!runId) return undefined;

    const stream = new RunEventStream(runId, {
      onEvent: (event) =>
        setEvents((current) => {
          const next = [...current, event];
          return next.length > MAX_BUFFERED_EVENTS
            ? next.slice(next.length - MAX_BUFFERED_EVENTS)
            : next;
        }),
      onStatus: setStreamStatus,
    });
    streamRef.current = stream;
    void stream.start();

    return () => {
      stream.close();
      streamRef.current = null;
    };
  }, [runId]);

  // Derived rather than written from the effect: with no run there is no stream, and
  // "idle" is a function of the argument rather than something to synchronise.
  return { events, status: runId ? streamStatus : "idle" };
}
