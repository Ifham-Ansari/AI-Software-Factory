import { expect, test } from "@playwright/test";
import { PASSWORD, fetchVerificationCode, registerAndSignIn, uniqueEmail } from "./helpers";

/**
 * The Phase 1 acceptance journey, end to end in a real browser:
 * register → verify email → create a project → see it listed → sign out → session rejected.
 */

test.describe("authentication", () => {
  test("register, create a project, sign out, and lose access", async ({ page }) => {
    await registerAndSignIn(page, "E2E User");

    await expect(page.getByTestId("current-user")).toHaveText("E2E User");

    // A brand-new account has no projects, and the empty state says what to do.
    await expect(page.getByText("No projects yet")).toBeVisible();

    await page.getByLabel("Name").fill("Restaurant System");
    await page.getByLabel("Description").fill("POS and inventory.");
    await page.getByRole("button", { name: "Create project" }).click();

    await expect(page.getByTestId("project-card")).toHaveCount(1);
    await expect(page.getByRole("link", { name: "Restaurant System" })).toBeVisible();

    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/login$/);

    // The session is genuinely gone: navigating back does not restore it.
    await page.goto("/projects");
    await expect(page).toHaveURL(/\/login$/);
  });

  test("sign in with an existing account", async ({ page }) => {
    const email = await registerAndSignIn(page, "Returning User");

    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/login$/);

    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page).toHaveURL(/\/projects$/);
    await expect(page.getByTestId("current-user")).toHaveText("Returning User");
  });

  test("rejects wrong credentials without revealing which half was wrong", async ({ page }) => {
    const email = await registerAndSignIn(page, "Someone");
    await page.getByRole("button", { name: "Sign out" }).click();

    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill("the-wrong-passphrase");
    await page.getByRole("button", { name: "Sign in" }).click();

    // Not getByRole("alert"): Next.js's route announcer also carries role="alert",
    // which makes that locator ambiguous. Match the message itself.
    await expect(page.getByText("Invalid email or password.")).toBeVisible();
    await expect(page).toHaveURL(/\/login$/);
  });

  test("shows validation errors on registration", async ({ page }) => {
    await page.goto("/register");
    await page.getByLabel("Name").fill("Ada");
    await page.getByLabel("Email").fill("not-an-email");
    await page.getByLabel("Password", { exact: true }).fill("short");
    await page.getByRole("button", { name: "Create account" }).click();

    await expect(page.getByText("Enter a valid email address")).toBeVisible();
    await expect(page).toHaveURL(/\/register$/);
  });

  test("signed-out visitors are sent to the sign-in page", async ({ page }) => {
    await page.goto("/projects");

    await expect(page).toHaveURL(/\/login$/);
  });

  test("verifies a new account with a 6-digit code, then can sign in without it", async ({
    page,
  }) => {
    const email = uniqueEmail();

    await page.goto("/register");
    await page.getByLabel("Name").fill("Code Entry");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
    await page.getByRole("button", { name: "Create account" }).click();

    await expect(page).toHaveURL(/\/verify-email/);
    await expect(page.getByText(email)).toBeVisible();

    // A wrong code is rejected without consuming the real one.
    for (const [index, digit] of "000000".split("").entries()) {
      await page.getByLabel(`Digit ${index + 1} of 6`).fill(digit);
    }
    await page.getByRole("button", { name: "Verify email" }).click();
    await expect(page.getByText(/invalid|incorrect|attempts/i)).toBeVisible();

    const code = await fetchVerificationCode(page, email);
    for (const [index, digit] of code.split("").entries()) {
      await page.getByLabel(`Digit ${index + 1} of 6`).fill(digit);
    }
    await page.getByRole("button", { name: "Verify email" }).click();

    await expect(page).toHaveURL(/\/projects$/);

    // Signing back in never re-prompts for a code once the account is verified.
    await page.getByRole("button", { name: "Sign out" }).click();
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/projects$/);
  });

  test("can resend a verification code", async ({ page }) => {
    const email = uniqueEmail();

    await page.goto("/register");
    await page.getByLabel("Name").fill("Resend User");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
    await page.getByRole("button", { name: "Create account" }).click();
    await expect(page).toHaveURL(/\/verify-email/);

    await page.getByRole("button", { name: "Resend code" }).click();
    await expect(page.getByText("A new code is on its way.")).toBeVisible();

    const code = await fetchVerificationCode(page, email);
    for (const [index, digit] of code.split("").entries()) {
      await page.getByLabel(`Digit ${index + 1} of 6`).fill(digit);
    }
    await page.getByRole("button", { name: "Verify email" }).click();
    await expect(page).toHaveURL(/\/projects$/);
  });
});
