"use server";

/**
 * Authentication actions.
 *
 * These are the session boundary. The API returns tokens in its response body; these
 * actions move them into httpOnly cookies and return only what the page needs. A token
 * never reaches browser JavaScript, so an XSS bug cannot steal a session.
 *
 * Failures are *returned*, not thrown: throwing would trip an error boundary and discard
 * the form the user just filled in.
 */

import { redirect } from "next/navigation";
import type { SessionResponse } from "@factory/contracts";
import { apiRequest } from "@/lib/api/client";
import { ApiError, toUserMessage } from "@/lib/api/errors";
import { clearSessionCookies, getRefreshToken, setSessionCookies } from "@/lib/auth/session";
import { failure, type FormState } from "@/lib/actions/state";
import { fieldErrors, registerSchema, signInSchema } from "@/lib/validation";

const PROJECTS_PATH = "/projects";

export async function registerAction(
  _previous: FormState,
  formData: FormData,
): Promise<FormState> {
  const parsed = registerSchema.safeParse({
    email: formData.get("email"),
    password: formData.get("password"),
    display_name: formData.get("display_name"),
  });

  if (!parsed.success) {
    return failure("Please correct the errors below.", fieldErrors(parsed.error));
  }

  try {
    const session = await apiRequest<SessionResponse>("/auth/register", {
      method: "POST",
      body: parsed.data,
      authenticated: false,
    });
    await setSessionCookies(session);
  } catch (error) {
    if (error instanceof ApiError && error.isValidationError) {
      return failure("Please correct the errors below.", error.fieldErrors());
    }
    return failure(toUserMessage(error));
  }

  // Outside the try: redirect() signals by throwing, and a catch would swallow it.
  redirect(PROJECTS_PATH);
}

export async function signInAction(
  _previous: FormState,
  formData: FormData,
): Promise<FormState> {
  const parsed = signInSchema.safeParse({
    email: formData.get("email"),
    password: formData.get("password"),
  });

  if (!parsed.success) {
    // Deliberately not field-specific. Telling a caller which half of a sign-in was
    // wrong is exactly the feedback an attacker wants.
    return failure("Invalid email or password.");
  }

  try {
    const session = await apiRequest<SessionResponse>("/auth/sign-in", {
      method: "POST",
      body: parsed.data,
      authenticated: false,
    });
    await setSessionCookies(session);
  } catch (error) {
    return failure(toUserMessage(error));
  }

  redirect(PROJECTS_PATH);
}

export async function signOutAction(): Promise<void> {
  const refreshToken = await getRefreshToken();

  if (refreshToken) {
    try {
      await apiRequest("/auth/sign-out", {
        method: "POST",
        body: { refresh_token: refreshToken },
        authenticated: false,
      });
    } catch (error) {
      // Logged, not surfaced. Whatever happened server-side, clicking "sign out" must
      // leave the browser signed out; a usable cookie surviving a failed network call is
      // the worst outcome of this action.
      console.warn("Sign-out revocation failed; clearing cookies anyway", error);
    }
  }

  await clearSessionCookies();
  redirect("/login");
}
