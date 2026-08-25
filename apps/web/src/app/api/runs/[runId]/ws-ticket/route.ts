import "server-only";

import { NextResponse } from "next/server";
import type { WebSocketTicketResponse } from "@factory/contracts";
import { apiRequest } from "@/lib/api/client";
import { errorResponse } from "@/lib/api/route-helpers";
import { WS_BASE_URL } from "@/lib/config";

/**
 * Mint a single-use ticket for a run's event socket.
 *
 * The browser cannot authenticate a WebSocket handshake with the session cookie — it is
 * httpOnly and same-site, and a cookie-authenticated socket is CSRF-prone anyway. So this
 * authenticated REST call exchanges the cookie for a ticket the socket accepts once.
 *
 * The response also carries the socket URL. That is deliberate: unlike REST, a WebSocket
 * cannot be proxied through a Next.js route handler, so the browser connects to the API
 * directly and has to be told where it is. Handing the URL back from an authenticated
 * endpoint keeps it out of the public bundle for anyone not signed in.
 */
export async function POST(
  _request: Request,
  context: { params: Promise<{ runId: string }> },
): Promise<NextResponse> {
  const { runId } = await context.params;

  try {
    const ticket = await apiRequest<WebSocketTicketResponse>(
      `/runs/${encodeURIComponent(runId)}/ws-ticket`,
      { method: "POST" },
    );
    return NextResponse.json({
      ...ticket,
      // Absolute URL assembled server-side, so the client never has to guess a scheme
      // or an origin.
      socket_url: `${WS_BASE_URL}${ticket.socket_path}?ticket=${encodeURIComponent(
        ticket.ticket,
      )}`,
    });
  } catch (error) {
    return errorResponse(error);
  }
}
