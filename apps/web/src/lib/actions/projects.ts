"use server";

/**
 * Project actions.
 *
 * Each mutation revalidates the affected paths so the server-rendered list reflects the
 * change without a client-side cache to keep in sync.
 *
 * None of these takes an owner: ownership comes from the access token the API client
 * attaches, and the backend scopes every query by it. There is no parameter here through
 * which a caller could reach another user's project.
 */

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import type { ProjectResponse } from "@factory/contracts";
import { apiRequest } from "@/lib/api/client";
import { ApiError, toUserMessage } from "@/lib/api/errors";
import { failure, type FormState } from "@/lib/actions/state";
import { createProjectSchema, fieldErrors, updateProjectSchema } from "@/lib/validation";

const PROJECTS_PATH = "/projects";

export async function createProjectAction(
  _previous: FormState,
  formData: FormData,
): Promise<FormState> {
  const parsed = createProjectSchema.safeParse({
    name: formData.get("name"),
    description: formData.get("description") ?? "",
  });

  if (!parsed.success) {
    return failure("Please correct the errors below.", fieldErrors(parsed.error));
  }

  try {
    await apiRequest<ProjectResponse>(PROJECTS_PATH, {
      method: "POST",
      body: parsed.data,
    });
  } catch (error) {
    if (error instanceof ApiError && error.isValidationError) {
      return failure("Please correct the errors below.", error.fieldErrors());
    }
    return failure(toUserMessage(error));
  }

  revalidatePath(PROJECTS_PATH);
  return { success: true };
}

export async function updateProjectAction(
  projectId: string,
  _previous: FormState,
  formData: FormData,
): Promise<FormState> {
  const parsed = updateProjectSchema.safeParse({
    name: formData.get("name") ?? undefined,
    description: formData.get("description") ?? undefined,
  });

  if (!parsed.success) {
    return failure("Please correct the errors below.", fieldErrors(parsed.error));
  }

  try {
    await apiRequest<ProjectResponse>(`${PROJECTS_PATH}/${projectId}`, {
      method: "PATCH",
      body: parsed.data,
    });
  } catch (error) {
    if (error instanceof ApiError && error.isValidationError) {
      return failure("Please correct the errors below.", error.fieldErrors());
    }
    return failure(toUserMessage(error));
  }

  revalidatePath(PROJECTS_PATH);
  revalidatePath(`${PROJECTS_PATH}/${projectId}`);
  return { success: true };
}

export async function archiveProjectAction(projectId: string): Promise<FormState> {
  try {
    await apiRequest<ProjectResponse>(`${PROJECTS_PATH}/${projectId}/archive`, {
      method: "POST",
    });
  } catch (error) {
    return failure(toUserMessage(error));
  }

  revalidatePath(PROJECTS_PATH);
  revalidatePath(`${PROJECTS_PATH}/${projectId}`);
  return { success: true };
}

export async function deleteProjectAction(projectId: string): Promise<FormState> {
  try {
    await apiRequest<void>(`${PROJECTS_PATH}/${projectId}`, { method: "DELETE" });
  } catch (error) {
    return failure(toUserMessage(error));
  }

  revalidatePath(PROJECTS_PATH);
  // Outside the try: redirect() signals by throwing, and a catch would swallow it.
  redirect(PROJECTS_PATH);
}
