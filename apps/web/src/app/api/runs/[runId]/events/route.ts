import "server-only";

import { NextResponse } from "next/server";
import type { EventPageResponse } from "@factory/contracts";
import { apiRequest } from "@/lib/api/client";
import { errorResponse } from "@/lib/api/route-helpers";

/**
 * Replay a run's events from a sequence cursor.
 *
 * Proxied rather than called directly from the browser for the same reason as every
 * other REST call: the access token lives in an httpOnly cookie the browser cannot read,
 * so the handler is what turns a cookie into an `Authorization` header.
 *
 * This is the half of the realtime contract that provides the *guarantee*. The socket is
 * a latency optimisation; this endpoint is how a client proves it missed nothing, by
 * asking for everything after the last sequence number it processed.
 */
export async function GET(
  request: Request,
  context: { params: Promise<{ runId: string }> },
): Promise<NextResponse> {
  const { runId } = await context.params;
  const url = new URL(request.url);

  // Only these two are forwarded. Passing the query string through wholesale would let a
  // caller inject parameters the backend has not agreed to accept.
  const afterSeq = url.searchParams.get("after_seq") ?? "0";
  const limit = url.searchParams.get("limit") ?? "100";

  try {
    const page = await apiRequest<EventPageResponse>(
      `/runs/${encodeURIComponent(runId)}/events?after_seq=${encodeURIComponent(
        afterSeq,
      )}&limit=${encodeURIComponent(limit)}`,
    );
    return NextResponse.json(page);
  } catch (error) {
    return errorResponse(error);
  }
}
