"use client";

import { useCallback, useState, useTransition } from "react";
import type { ProjectResponse } from "@factory/contracts";
import { Alert, Button, ConfirmDialog, useToast } from "@/components/ui";
import {
  archiveProjectAction,
  deleteProjectAction,
  unarchiveProjectAction,
} from "@/lib/actions/projects";
import { EditProjectDialog } from "./EditProjectDialog";

/**
 * Lifecycle controls for a single project.
 *
 * **Every state change is confirmed, including unarchiving.** Archiving previously fired
 * on a single click with no way back, so the only difference between archiving and
 * deleting was how long it took to notice; confirmation and `unarchiveProjectAction` are
 * two halves of that fix. Unarchiving was originally left unconfirmed on the grounds that
 * it is reversible — but it is still a change of state the user may not have meant to
 * make, it is the one action on this row a *stray* click can reach (it occupies the same
 * position as Archive), and a row where two of three controls ask and the third does not
 * is the kind of inconsistency that trains people to click without reading.
 *
 * **Only one action can be in flight at a time.** All three share a single transition, and
 * every control is disabled while it runs — otherwise a slow archive leaves Delete live
 * beside it, and the two race for the same project.
 *
 * **Failures are reported where the user is looking.** A failed confirmation leaves its
 * dialog open, and the page behind a dialog is inert and covered, so the message goes
 * inside the dialog. The inline alert on the page and the toast cover the same failure for
 * the actions that are not behind one — a success is proved by the page changing, so it
 * only needs a message that fades.
 */
export function ProjectActions({ project }: { project: ProjectResponse }) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<"archive" | "unarchive" | "delete" | null>(
    null,
  );
  const [editing, setEditing] = useState(false);
  const { notify } = useToast();
  const archived = project.status === "archived";

  // Stable, because EditProjectDialog closes itself from an effect keyed on the submission
  // it just made. A handler rebuilt on every render would re-run that effect against the
  // same successful state and announce the same save twice.
  const closeEditor = useCallback(() => setEditing(false), []);

  const run = (action: () => Promise<{ error?: string }>, successMessage?: string) => {
    setError(null);
    startTransition(async () => {
      const result = await action();
      if (result?.error) {
        setError(result.error);
        notify(result.error, { variant: "error" });
        return;
      }
      setConfirming(null);
      if (successMessage) notify(successMessage, { variant: "success" });
    });
  };

  const dismiss = () => {
    setConfirming(null);
    setError(null);
  };

  return (
    <div className="project-actions">
      {/* Only shown once no dialog is holding the error: the dialog reports its own. */}
      {error && confirming === null && <Alert variant="error">{error}</Alert>}

      <div className="project-actions-row">
        {archived ? (
          <Button variant="secondary" disabled={pending} onClick={() => setConfirming("unarchive")}>
            Unarchive
          </Button>
        ) : (
          <>
            <Button variant="secondary" disabled={pending} onClick={() => setEditing(true)}>
              Edit
            </Button>
            <Button variant="secondary" disabled={pending} onClick={() => setConfirming("archive")}>
              Archive
            </Button>
          </>
        )}

        <Button variant="ghost" disabled={pending} onClick={() => setConfirming("delete")}>
          Delete
        </Button>
      </div>

      <EditProjectDialog project={project} open={editing} onClose={closeEditor} />

      <ConfirmDialog
        open={confirming === "archive"}
        title="Archive this project?"
        description={`“${project.name}” becomes read-only and stops accepting changes. You can unarchive it again at any time.`}
        // Not just "Archive": the trigger behind it carries that label too, and two
        // controls with the same name in one view is ambiguous by voice and by
        // screen reader, whichever one happens to be reachable.
        confirmLabel="Yes, archive"
        pending={pending}
        error={error}
        onConfirm={() =>
          run(() => archiveProjectAction(project.id), `“${project.name}” archived.`)
        }
        onCancel={dismiss}
      />

      <ConfirmDialog
        open={confirming === "unarchive"}
        title="Unarchive this project?"
        description={`“${project.name}” returns to draft and starts accepting changes again. Nothing recorded against it is altered, and you can archive it again at any time.`}
        confirmLabel="Yes, unarchive"
        pending={pending}
        error={error}
        onConfirm={() =>
          run(() => unarchiveProjectAction(project.id), `“${project.name}” restored.`)
        }
        onCancel={dismiss}
      />

      <ConfirmDialog
        open={confirming === "delete"}
        title="Delete this project permanently?"
        description={`“${project.name}” and everything recorded against it will be removed. This cannot be undone.`}
        confirmLabel="Yes, delete"
        destructive
        pending={pending}
        error={error}
        onConfirm={() => run(() => deleteProjectAction(project.id))}
        onCancel={dismiss}
      />
    </div>
  );
}
