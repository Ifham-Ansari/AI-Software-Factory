"use client";

import { useActionState, useEffect } from "react";
import type { ProjectResponse } from "@factory/contracts";
import { Alert, Button, Field, TextareaField, useToast } from "@/components/ui";
import { updateProjectAction } from "@/lib/actions/projects";
import { initialFormState } from "@/lib/actions/state";
import { MAX_DESCRIPTION_LENGTH, MAX_PROJECT_NAME_LENGTH } from "@/lib/validation";

interface EditProjectFormProps {
  project: ProjectResponse;
  /** Called once the save has been accepted. */
  onSaved: () => void;
  onCancel: () => void;
  /** Reports the in-flight state to the dialog, which must not close mid-request. */
  onPendingChange: (pending: boolean) => void;
}

/**
 * The body of the edit dialog [F-221].
 *
 * Split from the dialog because the two need different lifetimes. The dialog stays mounted
 * while closed so the browser can animate `<dialog>` in and out; this form is remounted per
 * opening, which is what makes an abandoned edit — and the action state left behind by a
 * rejected save — start clean the next time rather than persisting into it.
 *
 * **A rejected save keeps what was typed.** React resets an uncontrolled form once its
 * action completes, and it does that whether the action succeeded or failed, so the
 * defaults have to come from the rejected submission rather than from the stored project.
 * Otherwise the form clears the text at the exact moment it asks the user to correct it.
 *
 * The id is bound into the action server-side rather than posted in a hidden field: a
 * hidden input is something a browser can be made to change, and this one selects the row
 * to write to. Ownership is still enforced by the backend regardless.
 */
export function EditProjectForm({
  project,
  onSaved,
  onCancel,
  onPendingChange,
}: EditProjectFormProps) {
  const [state, formAction, pending] = useActionState(
    updateProjectAction.bind(null, project.id),
    initialFormState,
  );
  const { notify } = useToast();

  useEffect(() => {
    onPendingChange(pending);
  }, [pending, onPendingChange]);

  // Keyed on `state`, not `state.success`: the flag stays true after the first successful
  // save, so a dependency on it would fire once and the second save would announce nothing.
  // `useActionState` returns a fresh object per submission, so identity is what separates
  // them.
  useEffect(() => {
    if (state.success) {
      notify("Project updated.", { variant: "success" });
      onSaved();
    }
  }, [state, notify, onSaved]);

  const errors = state.fieldErrors ?? {};
  const values = state.values ?? { name: project.name, description: project.description };

  return (
    <>
      {state.error && <Alert variant="error">{state.error}</Alert>}

      <form action={formAction} noValidate>
        <Field
          label="Name"
          name="name"
          type="text"
          required
          maxLength={MAX_PROJECT_NAME_LENGTH}
          defaultValue={values.name}
          error={errors.name}
        />
        <TextareaField
          label="Description"
          name="description"
          maxLength={MAX_DESCRIPTION_LENGTH}
          defaultValue={values.description}
          error={errors.description}
          hint="Optional. Leave it empty to clear it."
        />
        <div className="modal-footer">
          <Button variant="ghost" onClick={onCancel} disabled={pending}>
            Cancel
          </Button>
          <Button type="submit" loading={pending}>
            Save changes
          </Button>
        </div>
      </form>
    </>
  );
}
