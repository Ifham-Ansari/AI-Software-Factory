/**
 * Server-side configuration.
 *
 * Nothing here is `NEXT_PUBLIC_`, and that is the point: the browser never learns where
 * the API lives, because it never calls the API. Route handlers proxy every request.
 *
 * Importing this module from a client component is a build error, which is the enforcement
 * mechanism — `server-only` fails the bundle rather than silently shipping the value.
 */

import "server-only";

/** Base URL of the FastAPI backend, reachable only from the Next.js server. */
export const API_BASE_URL = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

/**
 * How long a fetch to the backend may take before it is abandoned.
 *
 * Generous by default. A write path is several database round trips plus a deliberately
 * slow password hash, and against a geographically distant or serverless database that
 * adds up: registration measured 7-10s with the database in another region. A timeout
 * tuned for a local database turns a slow-but-working signup into a hard failure.
 *
 * It still exists, and still matters: without it a hung backend would hold a Next.js
 * request open until the platform's own timeout fired, exhausting server capacity.
 */
export const API_TIMEOUT_MS = Number(process.env.API_TIMEOUT_MS ?? 30_000);

/**
 * Whether cookies require HTTPS.
 *
 * Always true in production. Left off in development so the app works over plain http on
 * localhost, where `Secure` cookies are simply dropped.
 */
export const COOKIES_SECURE = process.env.NODE_ENV === "production";

/**
 * Origin the browser opens the event WebSocket against.
 *
 * The one place the browser does learn where the API lives, and it is unavoidable: a
 * WebSocket cannot be proxied through a Next.js route handler the way every REST call is.
 *
 * It is not `NEXT_PUBLIC_`, though. The value is returned by the authenticated ws-ticket
 * route rather than compiled into the bundle, so it reaches signed-in callers only — and
 * the socket still requires a single-use ticket, so knowing the URL grants nothing.
 *
 * Derived from `API_BASE_URL` by default: http becomes ws, https becomes wss.
 */
export const WS_BASE_URL =
  process.env.WS_BASE_URL ?? API_BASE_URL.replace(/^http/, "ws");
