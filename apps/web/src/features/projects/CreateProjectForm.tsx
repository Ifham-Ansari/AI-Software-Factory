"use client";

import { useActionState, useEffect, useRef } from "react";
import { Alert, Button, Field, TextareaField, useToast } from "@/components/ui";
import { createProjectAction } from "@/lib/actions/projects";
import { initialFormState } from "@/lib/actions/state";
import { MAX_PROJECT_NAME_LENGTH } from "@/lib/validation";

/**
 * Create a project.
 *
 * The form clears itself on success so the next project can be typed straight away.
 * `revalidatePath` in the action refreshes the list behind it, so there is no client-side
 * cache here to keep in sync.
 *
 * Success is a toast rather than an inline alert: the form has just been emptied, and the
 * new project appears in the list beside it, so an alert above a blank form would sit
 * there describing something the user can already see. Validation errors stay inline —
 * they belong next to the field that caused them, and they are not transient.
 */
export function CreateProjectForm() {
  const [state, formAction, pending] = useActionState(createProjectAction, initialFormState);
  const formRef = useRef<HTMLFormElement>(null);
  const { notify } = useToast();

  // Depends on `state`, not `state.success`. The flag is `true` after every successful
  // create, so a dependency on it only changes once: the second project in a row would
  // leave the form uncleared and announce nothing. `useActionState` hands back a fresh
  // object per submission, so the identity is what actually distinguishes them.
  useEffect(() => {
    if (state.success) {
      formRef.current?.reset();
      notify("Project created.", { variant: "success" });
    }
  }, [state, notify]);

  const errors = state.fieldErrors ?? {};

  return (
    <section className="panel" aria-labelledby="create-project-heading">
      <h2 id="create-project-heading">New project</h2>

      {state.error && <Alert variant="error">{state.error}</Alert>}

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
