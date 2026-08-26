"use client";

import { useActionState, useEffect } from "react";
import type { EventResponse } from "@factory/contracts";
import { Alert, Button, useToast } from "@/components/ui";
import { ConnectionIndicator } from "@/features/runs/ConnectionIndicator";
import { initialFormState } from "@/lib/actions/state";
import { startNoopJobAction } from "@/lib/actions/runs";
import { useRunEvents } from "@/lib/ws/useRunEvents";

interface ActivityFeedProps {
  projectId: string;
  runId: string | null;
}

/**
 * Live activity for a run.
 *
 * Handles all four states a data-displaying component must: connecting, error/offline,
 * empty, and populated. "Empty" is the interesting one here — a run with no events yet is
 * normal, not a failure, and saying so is what stops it looking broken while idle.
 *
 * Queueing a job is acknowledged by a toast. The work itself reports through the event
 * stream below, so the only thing needing confirmation is that the request was accepted —
 * which is exactly the transient, already-finished kind of message a toast is for. The
 * offline and error notices stay inline: they describe an ongoing condition, not an
 * event, and a condition must not scroll away on a timer.
 */
export function ActivityFeed({ projectId, runId }: ActivityFeedProps) {
  const { events, status } = useRunEvents(runId);
  const [state, enqueue, pending] = useActionState(startNoopJobAction, initialFormState);
  const { notify } = useToast();

  // Keyed on the state object rather than a flag: queueing several jobs in a row must
  // acknowledge each one, and `success` is `true` for all of them after the first.
  useEffect(() => {
    if (state.success && state.message) notify(state.message, { variant: "success" });
  }, [state, notify]);

  return (
    <section className="panel activity-feed" aria-labelledby="activity-heading">
      <header className="activity-header">
        <h2 id="activity-heading">Activity</h2>
        <ConnectionIndicator status={status} />
      </header>

      {state.error && <Alert variant="error">{state.error}</Alert>}
      {status === "offline" && (
        <Alert variant="error">
          Lost contact with the server. Reconnecting — no events will be missed.
        </Alert>
      )}

      <form action={enqueue} className="activity-actions">
        <input type="hidden" name="project_id" value={projectId} />
        <input type="hidden" name="run_id" value={runId ?? ""} />
        <Button type="submit" variant="secondary" size="sm" loading={pending}>
          Run a test job
        </Button>
      </form>

      {events.length === 0 ? (
        <p className="activity-empty muted">
          {status === "connecting"
            ? "Connecting…"
            : "No activity yet. Start a test job to see events arrive live."}
        </p>
      ) : (
        <ol className="activity-list" data-testid="activity-list">
          {events.map((event) => (
            <ActivityRow key={event.event_id} event={event} />
          ))}
        </ol>
      )}
    </section>
  );
}

/** One event in the feed. */
function ActivityRow({ event }: { event: EventResponse }) {
  const payload = event.payload as { message?: string; fraction?: number | null };
  return (
    <li className="activity-row" data-testid="activity-row">
      <span className="activity-seq" aria-label="Sequence number">
        {event.seq}
      </span>
      <span className="activity-type">{event.type}</span>
      <span className="activity-message">{payload.message ?? ""}</span>
      <time className="activity-time" dateTime={event.occurred_at}>
        {formatTime(event.occurred_at)}
      </time>
    </li>
  );
}

/** Render a timestamp, tolerating one that will not parse rather than crashing the list. */
function formatTime(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? "unknown"
    : parsed.toLocaleTimeString(undefined, { hour12: false });
}
