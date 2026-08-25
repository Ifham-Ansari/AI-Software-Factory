import { expect, test, type Page } from "@playwright/test";
import { registerAndSignIn } from "./helpers";

/**
 * The Phase 2 realtime journey [F-211, F-212, F-215].
 *
 * Enqueue a `noop` job from the UI, watch its events arrive over the WebSocket, then kill
 * the socket and confirm the client recovers with no gap and no duplicates.
 *
 * The reconnection test is the one that matters. It is the acceptance criterion — "a
 * browser reconnecting after a disconnect sees every missed event, in order, once" — and
 * it is what lets the socket be treated as a latency optimisation rather than a source of
 * truth.
 *
 * Sockets are captured by wrapping `WebSocket` from the test, via `addInitScript`, rather
 * than by exposing a handle from application code. Production code should not carry a
 * test seam that only a test uses.
 */

/** Wrap `WebSocket` so the test can reach the sockets the page opens. */
async function captureSockets(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const opened: WebSocket[] = [];
    (window as unknown as { __sockets: WebSocket[] }).__sockets = opened;
    const Original = window.WebSocket;
    // Preserve the constructor's identity for anything doing instanceof checks.
    class Tracked extends Original {
      constructor(url: string | URL, protocols?: string | string[]) {
        super(url, protocols);
        opened.push(this);
      }
    }
    window.WebSocket = Tracked as unknown as typeof WebSocket;
  });
}

async function openAProject(page: Page): Promise<void> {
  await captureSockets(page);
  await registerAndSignIn(page, "Realtime User");
  await page.getByLabel("Name").fill("Realtime Project");
  await page.getByRole("button", { name: "Create project" }).click();
  await page.getByRole("link", { name: "Realtime Project" }).click();
  await expect(page.getByRole("heading", { name: "Realtime Project" })).toBeVisible();
}

/** Sequence numbers currently rendered in the feed, in display order. */
async function renderedSequences(page: Page): Promise<number[]> {
  const texts = await page
    .getByTestId("activity-row")
    .locator(".activity-seq")
    .allTextContents();
  return texts.map((value) => Number(value.trim()));
}

test.describe("realtime activity", () => {
  test("shows connection status and an empty state before anything happens", async ({
    page,
  }) => {
    await openAProject(page);

    // Connecting or live depending on how fast the socket opened; both mean "working".
    await expect(page.getByTestId("connection-status")).toHaveText(/Live|Connecting/);
    // Scoped to the empty-state paragraph: a bare text match also hits the status
    // indicator, which carries the same word.
    await expect(page.locator(".activity-empty")).toHaveText(/No activity yet|Connecting/);
    await expect(page.getByTestId("activity-row")).toHaveCount(0);
  });

  test("delivers job events live over the socket", async ({ page }) => {
    await openAProject(page);
    await expect(page.getByTestId("connection-status")).toHaveText("Live");

    await page.getByRole("button", { name: "Run a test job" }).click();

    // The noop handler emits one progress event per step.
    await expect(page.getByTestId("activity-row")).toHaveCount(3, { timeout: 30_000 });
    await expect(page.getByText("Step 3 of 3")).toBeVisible();
    expect(await renderedSequences(page)).toEqual([1, 2, 3]);
  });

  test("recovers from a dropped socket with no gap and no duplicates", async ({ page }) => {
    await openAProject(page);
    await expect(page.getByTestId("connection-status")).toHaveText("Live");

    await page.getByRole("button", { name: "Run a test job" }).click();
    await expect(page.getByTestId("activity-row")).toHaveCount(3, { timeout: 30_000 });

    // Simulate a network drop by closing every socket the page opened.
    await page.evaluate(() => {
      const sockets = (window as unknown as { __sockets?: WebSocket[] }).__sockets ?? [];
      for (const socket of sockets) socket.close();
    });

    // Enqueue more work while the client is reconnecting. These events are produced
    // during the outage, so they can only reach the feed through the replay.
    await page.getByRole("button", { name: "Run a test job" }).click();

    await expect(page.getByTestId("activity-row")).toHaveCount(6, { timeout: 60_000 });
    // The guarantee, checked rather than assumed: 1..6, each exactly once, in order.
    expect(await renderedSequences(page)).toEqual([1, 2, 3, 4, 5, 6]);
    await expect(page.getByTestId("connection-status")).toHaveText("Live");
  });

  test("the socket carries no commands", async ({ page }) => {
    // Architecture §10.2: server-to-client only. Anything a client sends is discarded,
    // and every action goes over authenticated REST instead.
    await openAProject(page);
    await expect(page.getByTestId("connection-status")).toHaveText("Live");

    await page.evaluate(() => {
      const sockets = (window as unknown as { __sockets?: WebSocket[] }).__sockets ?? [];
      sockets[0]?.send("please delete everything");
    });

    // The socket survives and stays live: the message was ignored, not acted on.
    await expect(page.getByTestId("connection-status")).toHaveText("Live");
    await expect(page.getByTestId("activity-row")).toHaveCount(0);
  });
});
