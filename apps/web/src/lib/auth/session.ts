/**
 * Session cookies.
 *
 * Tokens live in httpOnly cookies set by this Next.js server, never in `localStorage` and
 * never in a JavaScript-readable cookie. An XSS bug can then run arbitrary code in the
 * page and still not read the session, because the browser will not hand it over.
 *
 * `sameSite: "lax"` blocks the cookie on cross-site POSTs, which covers the CSRF cases
 * that matter here while still allowing normal top-level navigation into the app.
 */

import "server-only";

import { cookies } from "next/headers";
import type { SessionResponse } from "@factory/contracts";
import { COOKIES_SECURE } from "@/lib/config";

const ACCESS_COOKIE = "factory_access";
const REFRESH_COOKIE = "factory_refresh";

/**
 * The refresh cookie is scoped to the refresh and sign-out endpoints.
 *
 * A long-lived credential should not be attached to every request that happens to hit the
 * server. Narrowing the path means it is only ever sent where it is actually needed.
 */
const REFRESH_PATH = "/api/auth";

const baseOptions = {
  httpOnly: true,
  secure: COOKIES_SECURE,
  sameSite: "lax",
} as const;

/** Persist a session returned by the API. */
export async function setSessionCookies(session: SessionResponse): Promise<void> {
  const store = await cookies();
  store.set(ACCESS_COOKIE, session.access_token, {
    ...baseOptions,
    path: "/",
    maxAge: session.expires_in,
  });
  store.set(REFRESH_COOKIE, session.refresh_token, {
    ...baseOptions,
    path: REFRESH_PATH,
    maxAge: session.refresh_expires_in,
  });
}

/** Remove both cookies. Used on sign-out and whenever a session is rejected. */
export async function clearSessionCookies(): Promise<void> {
  const store = await cookies();
  store.set(ACCESS_COOKIE, "", { ...baseOptions, path: "/", maxAge: 0 });
  store.set(REFRESH_COOKIE, "", { ...baseOptions, path: REFRESH_PATH, maxAge: 0 });
}

/** The current access token, if one is set. */
export async function getAccessToken(): Promise<string | null> {
  return (await cookies()).get(ACCESS_COOKIE)?.value ?? null;
}

/** The current refresh token, if one is set. */
export async function getRefreshToken(): Promise<string | null> {
  return (await cookies()).get(REFRESH_COOKIE)?.value ?? null;
}

/**
 * Whether a session cookie is present.
 *
 * Presence is not validity: the token may be expired or revoked. Use this only to decide
 * where to send someone, never to grant access — the backend is the authority.
 */
export async function hasSession(): Promise<boolean> {
  return (await getAccessToken()) !== null;
}
