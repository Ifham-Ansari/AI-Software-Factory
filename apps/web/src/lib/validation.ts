/**
 * Client-side validation schemas.
 *
 * These mirror the backend's rules so a user gets immediate feedback instead of a round
 * trip. They are a convenience, never a control: the backend validates everything again,
 * because anything running in a browser can be bypassed.
 *
 * When a rule changes, it changes in both places. The duplication is deliberate and small.
 */

import { z } from "zod";

export const MIN_PASSWORD_LENGTH = 8;
export const MAX_PASSWORD_LENGTH = 128;
export const MAX_PROJECT_NAME_LENGTH = 120;
export const MAX_DESCRIPTION_LENGTH = 2000;

export const emailSchema = z
  .string()
  .min(1, "Email is required")
  .email("Enter a valid email address")
  .max(254, "That email address is too long");

export const passwordSchema = z
  .string()
  .min(MIN_PASSWORD_LENGTH, `Use at least ${MIN_PASSWORD_LENGTH} characters`)
  .max(MAX_PASSWORD_LENGTH, "That password is too long");

export const registerSchema = z.object({
  email: emailSchema,
  // Length is the requirement, not character classes: complexity rules push people toward
  // predictable substitutions without adding meaningful entropy.
  password: passwordSchema,
  display_name: z
    .string()
    .trim()
    .min(1, "Name is required")
    .max(120, "That name is too long"),
});

export const signInSchema = z.object({
  email: emailSchema,
  // No minimum here. Rejecting a short password at sign-in would reveal that the stored
  // one is longer, and an older account must still be able to sign in.
  password: z.string().min(1, "Password is required"),
});

export const createProjectSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, "Project name is required")
    .max(MAX_PROJECT_NAME_LENGTH, "That name is too long"),
  description: z
    .string()
    .trim()
    .max(MAX_DESCRIPTION_LENGTH, "That description is too long")
    .default(""),
});

export const updateProjectSchema = z.object({
  name: z.string().trim().min(1).max(MAX_PROJECT_NAME_LENGTH).optional(),
  description: z.string().trim().max(MAX_DESCRIPTION_LENGTH).optional(),
});

export type RegisterInput = z.infer<typeof registerSchema>;
export type SignInInput = z.infer<typeof signInSchema>;
export type CreateProjectInput = z.infer<typeof createProjectSchema>;

/** Flatten a Zod error into field-keyed messages for rendering next to inputs. */
export function fieldErrors(error: z.ZodError): Record<string, string> {
  const result: Record<string, string> = {};
  for (const issue of error.issues) {
    const key = issue.path.join(".");
    if (key && !(key in result)) {
      result[key] = issue.message;
    }
  }
  return result;
}
