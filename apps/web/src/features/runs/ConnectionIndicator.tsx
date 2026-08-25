import type { ConnectionStatus } from "@/lib/ws/stream";

/** Label and modifier class per status. */
const PRESENTATION: Record<ConnectionStatus, { label: string; modifier: string }> = {
  idle: { label: "Not connected", modifier: "idle" },
  connecting: { label: "Connecting", modifier: "pending" },
  live: { label: "Live", modifier: "live" },
  reconnecting: { label: "Reconnecting", modifier: "pending" },
  offline: { label: "Offline", modifier: "offline" },
};

/**
 * Whether the activity feed is currently receiving events.
 *
 * Spelled out as text rather than signalled by colour alone — a colour-only indicator is
 * invisible to a colourblind user and to a screen reader. `role="status"` announces a
 * change without stealing focus, which matters because this changes on every reconnect.
 */
export function ConnectionIndicator({ status }: { status: ConnectionStatus }) {
  const { label, modifier } = PRESENTATION[status];
  return (
    <span
      className={`connection-indicator connection-${modifier}`}
      role="status"
      data-testid="connection-status"
    >
      <span className="connection-dot" aria-hidden="true" />
      {label}
    </span>
  );
}
