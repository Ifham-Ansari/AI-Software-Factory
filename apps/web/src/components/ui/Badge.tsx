import type { ProjectStatus } from "@factory/contracts";

/**
 * A project's lifecycle state.
 *
 * The status is spelled out as text rather than encoded only in colour: colour alone
 * fails for colourblind users and disappears entirely in high-contrast modes.
 */
export function StatusBadge({ status }: { status: ProjectStatus | string }) {
  const label = status === "archived" ? "Archived" : "Draft";
  return (
    <span className={`badge badge-${status}`} data-testid="project-status">
      {label}
    </span>
  );
}
