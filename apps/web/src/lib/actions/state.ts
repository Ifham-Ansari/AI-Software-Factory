/**
 * Form action state.
 *
 * Server Actions report failure by returning a value, not by throwing: a thrown error
 * becomes an error boundary and loses the form the user just filled in. Returning state
 * lets the page re-render with the message attached to the right field.
 */

/** The result of a submitted form. */
export interface FormState {
  /** A message to show above the form. Absent when the submission succeeded. */
  error?: string;
  /** Messages keyed by field name, rendered next to the offending input. */
  fieldErrors?: Record<string, string>;
  /** Set on success for actions that stay on the page. */
  success?: boolean;
  /** A positive message to show above the form, e.g. after a resend. */
  message?: string;
}

/** The state a form starts in, before anything has been submitted. */
export const initialFormState: FormState = {};

/** Build a failure state from a top-level message. */
export function failure(error: string, fieldErrors?: Record<string, string>): FormState {
  return fieldErrors ? { error, fieldErrors } : { error };
}

/** Build a success state that stays on the page, with an informational message. */
export function success(message: string): FormState {
  return { success: true, message };
}
