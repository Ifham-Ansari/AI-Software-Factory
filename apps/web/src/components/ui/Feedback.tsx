import type { ReactNode } from "react";

/**
 * Every data-displaying view needs four states — loading, error, empty, populated — and
 * the first three are the ones that get skipped. Having them as components makes leaving
 * one out a visible omission.
 */

interface AlertProps {
  variant?: "error" | "success" | "info";
  children: ReactNode;
}

/**
 * A message about the outcome of an action.
 *
 * Errors use `role="alert"` so assistive technology announces them immediately;
 * non-urgent messages use `role="status"`, which waits for a pause in speech.
 */
export function Alert({ variant = "info", children }: AlertProps) {
  return (
    <div
      className={`alert alert-${variant}`}
      role={variant === "error" ? "alert" : "status"}
    >
      {children}
    </div>
  );
}

interface EmptyStateProps {
  title: string;
  description: string;
  action?: ReactNode;
}

/**
 * The state a collection is in before anything has been added.
 *
 * An empty list is a normal state, not an error, and it is the moment a new user is most
 * likely to be lost — so it explains what to do next rather than just saying "no items".
 */
export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <h2>{title}</h2>
      <p>{description}</p>
      {action}
    </div>
  );
}

/** A placeholder occupying roughly the space its content will fill. */
export function Skeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="skeleton-list" aria-hidden="true">
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="skeleton-row" />
      ))}
    </div>
  );
}

/** An accessible loading indicator for a whole region. */
export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div className="loading-state" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span>{label}…</span>
    </div>
  );
}
