"use client";

import { useState, useTransition } from "react";
import type { ProjectResponse } from "@factory/contracts";
import { Alert, Button } from "@/components/ui";
import { archiveProjectAction, deleteProjectAction } from "@/lib/actions/projects";

/**
 * Destructive controls for a single project.
 *
 * Deletion asks for confirmation first. Archiving does not: it is reversible in principle
 * and non-destructive, so a confirmation step would be friction without a payoff.
 */
export function ProjectActions({ project }: { project: ProjectResponse }) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const run = (action: () => Promise<{ error?: string }>) => {
    setError(null);
    startTransition(async () => {
      const result = await action();
      if (result?.error) setError(result.error);
    });
  };

  return (
    <div className="project-actions">
      {error && <Alert variant="error">{error}</Alert>}

      {project.status !== "archived" && (
        <Button
          variant="secondary"
          loading={pending}
          onClick={() => run(() => archiveProjectAction(project.id))}
        >
          Archive
        </Button>
      )}

      {confirmingDelete ? (
        <div className="confirm-row" role="group" aria-label="Confirm deletion">
          <span>Delete this project permanently?</span>
          <Button
            variant="danger"
            loading={pending}
            onClick={() => run(() => deleteProjectAction(project.id))}
          >
            Yes, delete
          </Button>
          <Button variant="ghost" onClick={() => setConfirmingDelete(false)}>
            Cancel
          </Button>
        </div>
      ) : (
        <Button variant="ghost" onClick={() => setConfirmingDelete(true)}>
          Delete
        </Button>
      )}
    </div>
  );
}
