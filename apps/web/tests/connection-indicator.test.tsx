import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ConnectionIndicator } from "@/features/runs/ConnectionIndicator";
import type { ConnectionStatus } from "@/lib/ws/stream";

/**
 * The connection indicator [F-215].
 *
 * Split from the stream's own tests because it answers a different question: not "did the
 * events arrive?" but "can the user tell whether they are arriving?". Status is spelled
 * out as text rather than signalled by colour, which is what these assert.
 */

describe("ConnectionIndicator", () => {
  it.each([
    ["live", "Live"],
    ["connecting", "Connecting"],
    ["reconnecting", "Reconnecting"],
    ["offline", "Offline"],
    ["idle", "Not connected"],
  ])("spells out %s as text, not colour alone", (status, label) => {
    render(<ConnectionIndicator status={status as ConnectionStatus} />);

    expect(screen.getByTestId("connection-status")).toHaveTextContent(label);
  });

  it("announces changes without stealing focus", () => {
    render(<ConnectionIndicator status="live" />);

    expect(screen.getByTestId("connection-status")).toHaveAttribute("role", "status");
  });
});
