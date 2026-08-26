"use client";

import { useEffect, useRef } from "react";
import { Button } from "./Button";
import { Modal } from "./Modal";

/**
 * Confirmation for an action that cannot be undone [F-218].
 *
 * Two details make this safer than a generic dialog, and both are deliberate:
 *
 * 1. **Cancel is focused on open, not confirm.** A modal that appears under a user's
 *    hands with the destructive button focused turns a stray Enter into a deletion. The
 *    safe choice takes the focus; the dangerous one has to be aimed at.
 * 2. **Backdrop dismissal is disabled while the action is running.** Closing mid-request
 *    would leave the user with no idea whether the deletion happened.
 *
 * `<dialog>` focuses its first focusable child by default, which would be whatever the
 * footer happens to order first — so focus is placed explicitly rather than left to
 * button order, which a later edit could silently reverse.
 */

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  cancelLabel?: string;
  /** Styles the confirm button as destructive. */
  destructive?: boolean;
  pending?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel = "Cancel",
  destructive = false,
  pending = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (open) cancelRef.current?.focus();
  }, [open]);

  return (
    <Modal
      open={open}
      onClose={pending ? () => undefined : onCancel}
      title={title}
      description={description}
      dismissOnBackdrop={!pending}
      footer={
        <>
          <Button ref={cancelRef} variant="ghost" onClick={onCancel} disabled={pending}>
            {cancelLabel}
          </Button>
          <Button
            variant={destructive ? "danger" : "primary"}
            onClick={onConfirm}
            loading={pending}
          >
            {confirmLabel}
          </Button>
        </>
      }
    />
  );
}
