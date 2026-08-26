"use client";

import { useState, useTransition } from "react";
import type { ProjectResponse } from "@factory/contracts";
import { Alert, Button, ConfirmDialog, useToast } from "@/components/ui";
import { archiveProjectAction, deleteProjectAction } from "@/lib/actions/projects";

/**
 * Destructive controls for a single project.
 *
 * Deletion asks for confirmation in a modal. Archiving does not: it is reversible in
 * principle and non-destructive, so a confirmation step would be friction without a payoff.
 *
 * **Why failures stay inline while successes become toasts.** A success is the end of the
 * story — the list behind has already changed to prove it, so a message that fades is
 * enough. A failure means the thing the user asked for did not happen, and they still have
 * to decide what to do; that must not disappear on a timer. The toast for a failure is
 * therefore a duplicate of the inline alert rather than a replacement for it, so the
 * outcome is announced even when the alert is scrolled out of view.
 *
 * Deletion navigates away on success, so it gets no toast here — there would be nothing
 * left to attach it to, and the destination proves the outcome.
 */
export function ProjectActions({ project }: { project: ProjectResponse }) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const { notify } = useToast();

  const run = (action: () => Promise<{ error?: string }>, successMessage?: string) => {
    setError(null);
    startTransition(async () => {
      const result = await action();
      if (result?.error) {
        setError(result.error);
        notify(result.error, { variant: "error" });
        return;
      }
      if (successMessage) notify(successMessage, { variant: "success" });
    });
  };

  return (
    <div className="project-actions">
      {error && <Alert variant="error">{error}</Alert>}

      {project.status !== "archived" && (
        <Button
          variant="secondary"
          loading={pending}
          onClick={() =>
            run(() => archiveProjectAction(project.id), `“${project.name}” archived.`)
          }
        >
          Archive
        </Button>
      )}

      <Button variant="ghost" onClick={() => setConfirmingDelete(true)}>
        Delete
      </Button>

      <ConfirmDialog
        open={confirmingDelete}
        title="Delete this project permanently?"
        description={`“${project.name}” and everything recorded against it will be removed. This cannot be undone.`}
        confirmLabel="Yes, delete"
        destructive
        pending={pending}
        onConfirm={() => run(() => deleteProjectAction(project.id))}
        onCancel={() => setConfirmingDelete(false)}
      />
    </div>
  );
}
