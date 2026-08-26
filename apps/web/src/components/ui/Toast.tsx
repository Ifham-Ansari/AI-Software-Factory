"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

/**
 * Transient notifications [F-217].
 *
 * **What belongs in a toast, and what does not.** A toast confirms the outcome of
 * something the user just did, and then disappears. That makes it the wrong place for
 * anything they still have to act on: validation errors stay inline next to the field
 * that caused them, and a failure that blocks progress stays on the page. A message
 * nobody can scroll back to is not a place to keep information.
 *
 * Errors therefore never auto-dismiss — `duration: 0` — because "your project was not
 * deleted" vanishing after four seconds is how a user ends up believing the opposite.
 *
 * **Announcement.** The viewport is always in the DOM, even with nothing in it. Assistive
 * technology only announces changes to a live region it was already observing, so a region
 * created at the same moment as its first message is usually missed entirely.
 */

export type ToastVariant = "success" | "error" | "info";

export interface ToastOptions {
  variant?: ToastVariant;
  /** Milliseconds on screen. `0` keeps it until dismissed; the default for errors. */
  duration?: number;
}

interface Toast extends Required<ToastOptions> {
  id: number;
  message: string;
}

/** Long enough to read a short sentence without being in the way. */
const DEFAULT_DURATION_MS = 4_500;

/** More than this on screen at once is noise; the oldest is dropped. */
const MAX_VISIBLE = 4;

interface ToastApi {
  notify: (message: string, options?: ToastOptions) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

/**
 * Access the notifier.
 *
 * Throws when used outside the provider rather than silently doing nothing: a toast that
 * never appears is invisible in exactly the situation you need it.
 */
export function useToast(): ToastApi {
  const api = useContext(ToastContext);
  if (api === null) {
    throw new Error("useToast must be used inside <ToastProvider>");
  }
  return api;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(0);

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const notify = useCallback((message: string, options: ToastOptions = {}) => {
    const variant = options.variant ?? "info";
    setToasts((current) => {
      const toast: Toast = {
        id: nextId.current++,
        message,
        variant,
        // Errors are sticky unless the caller insists otherwise.
        duration: options.duration ?? (variant === "error" ? 0 : DEFAULT_DURATION_MS),
      };
      return [...current, toast].slice(-MAX_VISIBLE);
    });
  }, []);

  const api = useMemo(() => ({ notify }), [notify]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <ToastViewport toasts={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  );
}

function ToastViewport({
  toasts,
  onDismiss,
}: {
  toasts: Toast[];
  onDismiss: (id: number) => void;
}) {
  return (
    <div className="toast-viewport" data-testid="toast-viewport">
      {/* Polite: a toast reports something already finished, so it should wait for a
          pause rather than interrupt whatever is being read. Errors override this
          per-toast with role="alert". */}
      <ol aria-live="polite" aria-relevant="additions" className="toast-list">
        {toasts.map((toast) => (
          <ToastItem key={toast.id} toast={toast} onDismiss={onDismiss} />
        ))}
      </ol>
    </div>
  );
}

function ToastItem({ toast, onDismiss }: { toast: Toast; onDismiss: (id: number) => void }) {
  const [paused, setPaused] = useState(false);
  const remaining = useRef(toast.duration);

  /**
   * Own the dismissal timer, pausing while hovered or focused.
   *
   * The cleanup deducts the elapsed time, so pausing and resuming continues the countdown
   * instead of restarting it — a toast the user reached for should not outlive the reach,
   * nor reset every time the pointer crosses it.
   */
  useEffect(() => {
    if (toast.duration === 0 || paused) return undefined;
    const startedAt = Date.now();
    const timer = setTimeout(() => onDismiss(toast.id), remaining.current);
    return () => {
      clearTimeout(timer);
      remaining.current -= Date.now() - startedAt;
    };
  }, [paused, toast.duration, toast.id, onDismiss]);

  return (
    <li
      className={`toast toast-${toast.variant}`}
      data-testid="toast"
      // Errors interrupt; everything else waits its turn.
      role={toast.variant === "error" ? "alert" : "status"}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocusCapture={() => setPaused(true)}
      onBlurCapture={() => setPaused(false)}
    >
      <span className="toast-icon" aria-hidden="true" />
      <span className="toast-message">{toast.message}</span>
      <button
        type="button"
        className="toast-dismiss"
        onClick={() => onDismiss(toast.id)}
        aria-label="Dismiss notification"
      >
        ×
      </button>
    </li>
  );
}
