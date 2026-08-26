"use client";

import { useState, useTransition } from "react";
import type { ProjectResponse } from "@factory/contracts";
import { Alert, Button, ConfirmDialog, useToast } from "@/components/ui";
import {
  archiveProjectAction,
  deleteProjectAction,
  unarchiveProjectAction,
} from "@/lib/actions/projects";

/**
 * Lifecycle controls for a single project.
 *
 * **Archiving asks for confirmation, and can be undone.** It previously did neither: it
 * fired on a single click, and nothing could bring a project back, so the only difference
 * between archiving and deleting was how long it took to notice. Confirmation and
 * `unarchiveProjectAction` are two halves of the same fix — a confirmation on a one-way
 * door is still a one-way door, and a reversible action nobody was warned about is still
 * a surprise.
 *
 * **Unarchiving is not confirmed.** It is not destructive, it is trivially reversible by
 * archiving again, and a prompt on a safe action teaches people to dismiss prompts.
 *
 * **Failures stay inline as well as being announced.** A success is proved by the page
 * behind it changing, so a message that fades is enough. A failure means what the user
 * asked for did not happen and they still have to decide what to do, so it also stays on
 * the page — the toast duplicates it rather than replacing it.
 */
export function ProjectActions({ project }: { project: ProjectResponse }) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<"archive" | "delete" | null>(null);
  const { notify } = useToast();
  const archived = project.status === "archived";

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

  return (
    <div className="project-actions">
      {error && <Alert variant="error">{error}</Alert>}

      <div className="project-actions-row">
        {archived ? (
          <Button
            variant="secondary"
            loading={pending}
            onClick={() =>
              run(() => unarchiveProjectAction(project.id), `“${project.name}” restored.`)
            }
          >
            Unarchive
          </Button>
        ) : (
          <Button variant="secondary" onClick={() => setConfirming("archive")}>
            Archive
          </Button>
        )}

        <Button variant="ghost" onClick={() => setConfirming("delete")}>
          Delete
        </Button>
      </div>

      <ConfirmDialog
        open={confirming === "archive"}
        title="Archive this project?"
        description={`“${project.name}” becomes read-only and stops accepting changes. You can unarchive it again at any time.`}
        // Not just "Archive": the trigger behind it carries that label too, and two
        // controls with the same name in one view is ambiguous by voice and by
        // screen reader, whichever one happens to be reachable.
        confirmLabel="Yes, archive"
        pending={pending}
        onConfirm={() =>
          run(() => archiveProjectAction(project.id), `“${project.name}” archived.`)
        }
        onCancel={() => setConfirming(null)}
      />

      <ConfirmDialog
        open={confirming === "delete"}
        title="Delete this project permanently?"
        description={`“${project.name}” and everything recorded against it will be removed. This cannot be undone.`}
        confirmLabel="Yes, delete"
        destructive
        pending={pending}
        onConfirm={() => run(() => deleteProjectAction(project.id))}
        onCancel={() => setConfirming(null)}
      />
    </div>
  );
}
