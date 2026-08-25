"use server";

/**
 * Run and job actions.
 *
 * Every client action is an authenticated, audited REST call — never a WebSocket message.
 * The socket is server-to-client only, so there is one command path and one place that
 * enforces authorization (architecture.md §10.2).
 */

import { revalidatePath } from "next/cache";
import type { JobResponse, RunResponse } from "@factory/contracts";
import { apiRequest } from "@/lib/api/client";
import { toUserMessage } from "@/lib/api/errors";
import { failure, success, type FormState } from "@/lib/actions/state";

/** Create a run for a project, returning its id. */
export async function createRunAction(
  _previous: FormState,
  formData: FormData,
): Promise<FormState> {
  const projectId = formData.get("project_id");
  if (typeof projectId !== "string" || !projectId) {
    return failure("Missing project.");
  }

  try {
    await apiRequest<RunResponse>(`/projects/${encodeURIComponent(projectId)}/runs`, {
      method: "POST",
    });
  } catch (error) {
    return failure(toUserMessage(error));
  }

  revalidatePath(`/projects/${projectId}`);
  return success("Run created.");
}

/**
 * Enqueue the `noop` job against a run.
 *
 * The Phase 2 pipeline proof: it does no real work, and exists so the whole chain —
 * enqueue, claim, execute, persist, publish, fan out to this browser — is demonstrable
 * before any agent exists to drive it.
 */
export async function startNoopJobAction(
  _previous: FormState,
  formData: FormData,
): Promise<FormState> {
  const runId = formData.get("run_id");
  if (typeof runId !== "string" || !runId) {
    return failure("This project has no run yet.");
  }

  try {
    await apiRequest<JobResponse>(`/runs/${encodeURIComponent(runId)}/jobs`, {
      method: "POST",
      body: { type: "noop", steps: 3 },
    });
  } catch (error) {
    return failure(toUserMessage(error));
  }

  // No revalidation: the result arrives over the event stream, which is the point of
  // this feature. Refreshing the page would defeat the demonstration.
  return success("Job queued.");
}
