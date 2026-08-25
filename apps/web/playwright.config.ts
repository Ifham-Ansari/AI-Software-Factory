import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end configuration.
 *
 * These specs drive a real browser against the real stack — Next.js, FastAPI and
 * PostgreSQL. They are the only tests that prove the whole chain works together, and the
 * only ones that would catch a cookie flag or a redirect being wrong.
 *
 * The stack must already be running. Playwright does not start it because the API needs a
 * migrated database, and a `webServer` block that silently fails to connect produces a
 * confusing timeout instead of a clear "your stack is not up" message.
 *
 *   Terminal 1:  EMAIL__TRANSPORT=console VERIFICATION__RESEND_COOLDOWN_SECONDS=0 uv run dev-api
 *   Terminal 2:  uv run dev-worker
 *   Terminal 3:  pnpm --filter web dev
 *   Terminal 4:  pnpm --filter web test:e2e
 *
 * The two API overrides matter, and a populated .env will otherwise break the run:
 *
 *   - `EMAIL__TRANSPORT=console` — registration codes are read from the debug endpoint,
 *     which has nothing to read if mail actually went out over SMTP.
 *   - `VERIFICATION__RESEND_COOLDOWN_SECONDS=0` — the real 60s cooldown makes the resend
 *     spec race a production rate limit. That enforcement is proven in the unit suite.
 *
 * The worker is not optional: the realtime specs enqueue a job and wait for its events,
 * and with nothing to claim it they time out.
 *
 * CI sets all of this and starts every process before invoking this; see
 * .github/workflows/ci.yml, which runs the suite twice — once with Redis fan-out enabled
 * and once with it unavailable.
 */
const BASE_URL = process.env.E2E_BASE_URL ?? "http://127.0.0.1:3000";

export default defineConfig({
  testDir: "./e2e",
  // Each spec registers its own account, so they do not contend for shared state.
  fullyParallel: true,
  // A test that only passes on a retry is a flaky test; in CI that must be visible.
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  // A registration round trip against a remote database can take ~10s, so the
  // per-assertion timeout has to clear that or the suite fails on latency alone.
  timeout: 60_000,
  expect: { timeout: 20_000 },

  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },

  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
