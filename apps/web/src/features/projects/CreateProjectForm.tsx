"use client";

import { useActionState, useEffect, useRef } from "react";
import { Alert, Button, Field, TextareaField } from "@/components/ui";
import { createProjectAction } from "@/lib/actions/projects";
import { initialFormState } from "@/lib/actions/state";
import { MAX_PROJECT_NAME_LENGTH } from "@/lib/validation";

/**
 * Create a project.
 *
 * The form clears itself on success so the next project can be typed straight away.
 * `revalidatePath` in the action refreshes the list behind it, so there is no client-side
 * cache here to keep in sync.
 */
export function CreateProjectForm() {
  const [state, formAction, pending] = useActionState(createProjectAction, initialFormState);
  const formRef = useRef<HTMLFormElement>(null);

  useEffect(() => {
    if (state.success) {
      formRef.current?.reset();
    }
  }, [state.success]);

  const errors = state.fieldErrors ?? {};

  return (
    <section className="panel" aria-labelledby="create-project-heading">
      <h2 id="create-project-heading">New project</h2>

      {state.error && <Alert variant="error">{state.error}</Alert>}
      {state.success && <Alert variant="success">Project created.</Alert>}

      <form ref={formRef} action={formAction} noValidate>
        <Field
          label="Name"
          name="name"
          type="text"
          required
          maxLength={MAX_PROJECT_NAME_LENGTH}
          placeholder="Restaurant management system"
          error={errors.name}
        />
        <TextareaField
          label="Description"
          name="description"
          placeholder="What should it do?"
          error={errors.description}
          hint="Optional. You can add this later."
        />
        <Button type="submit" loading={pending}>
          Create project
        </Button>
      </form>
    </section>
  );
}
