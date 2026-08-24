import { expect, type Page } from "@playwright/test";

/**
 * Shared e2e fixtures.
 *
 * Registration is two steps — a code is emailed, then redeemed — so every spec that needs
 * a signed-in user goes through the same path. The code itself comes from a debug endpoint
 * that only exists in development/test (see `factory_api.routers.debug`): the service
 * never returns or logs a code by design, so this is the only way a browser-driven test
 * can read one without a real mailbox.
 */

const API_BASE_URL = process.env.E2E_API_BASE_URL ?? "http://127.0.0.1:8000";

export const PASSWORD = "an-e2e-passphrase-long-enough";

/** A fresh address per call, so parallel tests never contend for one account. */
export function uniqueEmail(): string {
  return `e2e-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;
}

/** Read the most recent verification code sent to an address. */
export async function fetchVerificationCode(page: Page, email: string): Promise<string> {
  const response = await page.request.get(
    `${API_BASE_URL}/debug/verification-code?email=${encodeURIComponent(email)}`,
  );
  if (!response.ok()) {
    throw new Error(
      `No verification code available for ${email} (status ${response.status()})`,
    );
  }
  const body = (await response.json()) as { code: string };
  return body.code;
}

/** Fill the six-box code input, one digit per box. */
export async function fillVerificationCode(page: Page, code: string): Promise<void> {
  for (const [index, digit] of code.split("").entries()) {
    await page.getByLabel(`Digit ${index + 1} of ${code.length}`).fill(digit);
  }
}

/** Register a new account, redeem its code, and land signed in on /projects. */
export async function registerAndSignIn(
  page: Page,
  name = "E2E User",
  email: string = uniqueEmail(),
): Promise<string> {
  await page.goto("/register");
  await page.getByLabel("Name").fill(name);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();

  await expect(page).toHaveURL(/\/verify-email/);
  const code = await fetchVerificationCode(page, email);
  await fillVerificationCode(page, code);
  await page.getByRole("button", { name: "Verify email" }).click();

  await expect(page).toHaveURL(/\/projects$/);
  return email;
}
