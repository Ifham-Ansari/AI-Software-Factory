/**
 * Error handling for API responses.
 *
 * The backend returns one envelope for every failure, with a stable `error.code`. Client
 * code branches on the code, never on status text or message wording — those are for
 * humans and are free to change.
 */

import type { ErrorBody, ErrorResponse } from "@factory/contracts";

/** A failure returned by the API, carrying its stable code. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fields: ReadonlyArray<{ field: string; message: string }>;
  readonly requestId: string | null;

  constructor(status: number, body: ErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.fields = body.fields ?? [];
    this.requestId = body.request_id ?? null;
  }

  /** Whether the caller needs to sign in again. */
  get isAuthError(): boolean {
    return this.status === 401;
  }

  /** Whether the request itself was malformed or invalid. */
  get isValidationError(): boolean {
    return this.code === "validation_failed";
  }

  /** Field-level messages, keyed by field name, for rendering next to inputs. */
  fieldErrors(): Record<string, string> {
    return Object.fromEntries(this.fields.map((f) => [f.field, f.message]));
  }
}

/** Raised when the backend cannot be reached at all. */
export class ApiUnreachableError extends Error {
  constructor(cause?: unknown) {
    super("The service is temporarily unavailable. Please try again.");
    this.name = "ApiUnreachableError";
    this.cause = cause;
  }
}

/**
 * Build an `ApiError` from a failed response.
 *
 * Falls back to a synthetic envelope when the body is not the expected shape — a proxy
 * returning an HTML error page, for instance. Callers must never have to handle a
 * "response was not JSON" case themselves.
 */
export async function toApiError(response: Response): Promise<ApiError> {
  try {
    const body = (await response.json()) as ErrorResponse;
    if (body?.error?.code) {
      return new ApiError(response.status, body.error);
    }
  } catch {
    // Falls through to the synthetic envelope below.
  }
  return new ApiError(response.status, {
    code: "internal_error",
    message: "An unexpected error occurred.",
    details: {},
    fields: [],
    request_id: response.headers.get("X-Request-ID"),
  });
}

/** Turn any thrown value into a message safe to show a user. */
export function toUserMessage(error: unknown): string {
  if (error instanceof ApiError || error instanceof ApiUnreachableError) {
    return error.message;
  }
  return "An unexpected error occurred. Please try again.";
}
