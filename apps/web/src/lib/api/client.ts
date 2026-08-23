/**
 * Server-side API client.
 *
 * The only place that talks to FastAPI. Server Components call it to load data; route
 * handlers call it to proxy browser actions. It attaches the access token from the
 * httpOnly cookie, so no caller ever handles a token.
 *
 * Every request carries a timeout. A backend that hangs would otherwise hold a Next.js
 * server request open until the platform's own timeout fires, turning one slow dependency
 * into exhausted server capacity.
 */

import "server-only";

import { API_BASE_URL, API_TIMEOUT_MS } from "@/lib/config";
import { ApiError, ApiUnreachableError, toApiError } from "@/lib/api/errors";
import { getAccessToken } from "@/lib/auth/session";

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  /** Attach the caller's access token. Off for register/sign-in, which have none yet. */
  authenticated?: boolean;
  /** Forwarded so a browser action and its backend call share one correlation id. */
  requestId?: string | null;
}

/**
 * Perform a request against the backend.
 *
 * @throws ApiError When the backend returns a non-2xx response.
 * @throws ApiUnreachableError When the backend cannot be reached or times out.
 */
export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, authenticated = true, requestId } = options;

  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (requestId) headers["X-Request-ID"] = requestId;

  if (authenticated) {
    const token = await getAccessToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(API_TIMEOUT_MS),
      // Never cache: everything here is per-user and authenticated. A shared cache
      // entry would serve one user's data to another.
      cache: "no-store",
    });
  } catch (cause) {
    throw new ApiUnreachableError(cause);
  }

  if (!response.ok) {
    throw await toApiError(response);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

/**
 * Perform a request, returning `null` instead of throwing when unauthenticated.
 *
 * Server Components use this to render a signed-out view rather than crashing the page
 * when a token has expired between navigations.
 */
export async function apiRequestOrNull<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T | null> {
  try {
    return await apiRequest<T>(path, options);
  } catch (error) {
    if (error instanceof ApiError && error.isAuthError) {
      return null;
    }
    throw error;
  }
}
