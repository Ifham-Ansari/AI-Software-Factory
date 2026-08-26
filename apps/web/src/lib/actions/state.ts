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
  /**
   * What was submitted, returned so a rejected form can re-render still holding it.
   *
   * React resets an uncontrolled form once its action completes — including when the
   * action failed — so without this a validation error throws away the very text the user
   * is being asked to correct. Populate it only with fields that are safe to echo back:
   * never a password, never anything derived from a secret.
   */
  values?: Record<string, string>;
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
