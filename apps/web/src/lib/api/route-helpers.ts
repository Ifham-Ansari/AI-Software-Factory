/**
 * Shared plumbing for the auth route handlers.
 *
 * These handlers are the boundary where a browser action becomes a backend call. They
 * exist so the browser never holds a token: the request arrives with a cookie, the handler
 * unwraps it, calls the API, and writes any new tokens back as cookies.
 */

import "server-only";

import { NextResponse } from "next/server";
import { ApiError, ApiUnreachableError } from "@/lib/api/errors";

/** Render a thrown error as the same envelope shape the backend uses. */
export function errorResponse(error: unknown): NextResponse {
  if (error instanceof ApiError) {
    return NextResponse.json(
      {
        error: {
          code: error.code,
          message: error.message,
          fields: error.fields,
          request_id: error.requestId,
        },
      },
      { status: error.status },
    );
  }

  if (error instanceof ApiUnreachableError) {
    return NextResponse.json(
      { error: { code: "service_unavailable", message: error.message, fields: [] } },
      { status: 503 },
    );
  }

  // Nothing about an unexpected failure reaches the client: a stack trace would expose
  // paths and versions, and there is nothing here a user could act on.
  console.error("Unhandled route error", error);
  return NextResponse.json(
    {
      error: {
        code: "internal_error",
        message: "An unexpected error occurred.",
        fields: [],
      },
    },
    { status: 500 },
  );
}

/** Parse a JSON request body, returning `null` when it is not valid JSON. */
export async function readJson(request: Request): Promise<unknown | null> {
  try {
    return await request.json();
  } catch {
    return null;
  }
}

/** The standard response for a malformed request body. */
export function badRequest(message = "The request body was malformed."): NextResponse {
  return NextResponse.json(
    { error: { code: "malformed_request", message, fields: [] } },
    { status: 400 },
  );
}
