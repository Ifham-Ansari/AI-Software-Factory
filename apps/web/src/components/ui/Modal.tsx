"use client";

import { useEffect, useRef, useId, type ReactNode } from "react";

/**
 * A modal dialog [F-218].
 *
 * Built on the native `<dialog>` element with `showModal()`, which is not a shortcut — it
 * is the correct implementation. The browser gives us, for free and correctly:
 *
 * * **focus containment**, including the cases hand-rolled traps get wrong (shadow DOM,
 *   iframes, browser UI, the address bar),
 * * **`inert` background**, so the page behind is unreachable by keyboard *and* hidden
 *   from assistive technology,
 * * **Escape to dismiss**, delivered as a `cancel` event,
 * * **focus restored** to whatever was focused before it opened,
 * * the **top layer**, so it cannot be trapped under a stacking context — the bug that
 *   makes hand-written modals disappear behind a sticky header.
 *
 * A JavaScript focus trap reimplements all of that, badly. The one thing we must add is
 * keeping React state as the source of truth: the browser can close the dialog on its own
 * (Escape), so `cancel` is intercepted and routed back through `onClose`, or the prop and
 * the DOM would disagree about whether the dialog is open.
 */

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  /** Optional supporting text, announced with the title. */
  description?: string;
  children?: ReactNode;
  /** Action buttons. Rendered in the dialog's footer. */
  footer?: ReactNode;
  /** Whether clicking the backdrop closes. Off for dialogs mid-operation. */
  dismissOnBackdrop?: boolean;
}

export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  dismissOnBackdrop = true,
}: ModalProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (dialog === null) return;
    // Guarded both ways: calling showModal() on an open dialog throws, and close() on a
    // closed one fires a spurious `close` event.
    if (open && !dialog.open) {
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  return (
    <dialog
      ref={ref}
      className="modal"
      aria-labelledby={titleId}
      aria-describedby={description ? descriptionId : undefined}
      onCancel={(event) => {
        // Escape. Prevented so the browser does not close it behind React's back, leaving
        // `open` true against a closed dialog — after which nothing reopens it.
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        // The backdrop is not a separate element: a click that lands on the dialog itself
        // rather than on the panel inside it came from outside the panel.
        if (dismissOnBackdrop && event.target === ref.current) onClose();
      }}
    >
      <div className="modal-panel">
        <h2 className="modal-title" id={titleId}>
          {title}
        </h2>
        {description && (
          <p className="modal-description" id={descriptionId}>
            {description}
          </p>
        )}
        {children && <div className="modal-body">{children}</div>}
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </dialog>
  );
}
