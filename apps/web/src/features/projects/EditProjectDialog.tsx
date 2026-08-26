"use client";

import { useCallback, useState } from "react";
import type { ProjectResponse } from "@factory/contracts";
import { Modal } from "@/components/ui";
import { EditProjectForm } from "./EditProjectForm";

interface EditProjectDialogProps {
  project: ProjectResponse;
  open: boolean;
  onClose: () => void;
}

/**
 * Edit a project's name and description [F-221].
 *
 * **Only the two fields the API accepts are editable.** The slug is derived from the name
 * by the backend — offering it here would let the two disagree — and status is a lifecycle
 * decision with its own controls.
 *
 * This component is the shell: the modal, and the rule about when its contents are allowed
 * to start over. The form inside is remounted on every opening, so an abandoned edit and
 * the action state left by a rejected save do not survive into the next one. Keying rather
 * than unmounting the whole dialog, because the dialog has to stay mounted while closed for
 * the browser to animate it out — unmounting it would make it vanish instead.
 *
 * While a save is in flight the dialog cannot be dismissed, by backdrop or by Escape:
 * closing mid-request leaves the user unable to tell whether the change was made.
 */
export function EditProjectDialog({ project, open, onClose }: EditProjectDialogProps) {
  const [openings, setOpenings] = useState(0);
  const [wasOpen, setWasOpen] = useState(open);
  const [pending, setPending] = useState(false);

  // Derived during render rather than in an Effect: this is state computed from other
  // state, not a synchronization with anything outside React, and an Effect would render
  // one frame with the previous opening's contents before correcting itself.
  if (open !== wasOpen) {
    setWasOpen(open);
    if (open) setOpenings((count) => count + 1);
  }

  // Stable, because the form closes the dialog from an Effect keyed on the submission it
  // just made. A handler rebuilt every render would re-run that Effect against the same
  // successful state and announce the same save twice.
  const close = useCallback(() => onClose(), [onClose]);

  return (
    <Modal
      open={open}
      onClose={pending ? () => undefined : onClose}
      title="Edit project"
      description="Change the name or description. Everything else stays as it is."
      dismissOnBackdrop={!pending}
    >
      <EditProjectForm
        key={openings}
        project={project}
        onSaved={close}
        onCancel={close}
        onPendingChange={setPending}
      />
    </Modal>
  );
}
