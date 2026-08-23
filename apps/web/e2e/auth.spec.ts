import { expect, test } from "@playwright/test";

/**
 * The Phase 1 acceptance journey, end to end in a real browser:
 * register → create a project → see it listed → sign out → session rejected.
 */

/** A fresh address per test, so parallel runs never contend for one account. */
function uniqueEmail(): string {
  return `e2e-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.test`;
}

const PASSWORD = "an-e2e-passphrase-long-enough";

test.describe("authentication", () => {
  test("register, create a project, sign out, and lose access", async ({ page }) => {
    const email = uniqueEmail();

    await page.goto("/register");
    await page.getByLabel("Name").fill("E2E User");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: "Create account" }).click();

    // Registration signs the user straight in.
    await expect(page).toHaveURL(/\/projects$/);
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
    const email = uniqueEmail();

    await page.goto("/register");
    await page.getByLabel("Name").fill("Returning User");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: "Create account" }).click();
    await expect(page).toHaveURL(/\/projects$/);

    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/login$/);

    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page).toHaveURL(/\/projects$/);
    await expect(page.getByTestId("current-user")).toHaveText("Returning User");
  });

  test("rejects wrong credentials without revealing which half was wrong", async ({ page }) => {
    const email = uniqueEmail();

    await page.goto("/register");
    await page.getByLabel("Name").fill("Someone");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: "Create account" }).click();
    await expect(page).toHaveURL(/\/projects$/);
    await page.getByRole("button", { name: "Sign out" }).click();

    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill("the-wrong-passphrase");
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page.getByRole("alert")).toContainText("Invalid email or password");
    await expect(page).toHaveURL(/\/login$/);
  });

  test("shows validation errors on registration", async ({ page }) => {
    await page.goto("/register");
    await page.getByLabel("Name").fill("Ada");
    await page.getByLabel("Email").fill("not-an-email");
    await page.getByLabel("Password").fill("short");
    await page.getByRole("button", { name: "Create account" }).click();

    await expect(page.getByText("Enter a valid email address")).toBeVisible();
    await expect(page).toHaveURL(/\/register$/);
  });

  test("signed-out visitors are sent to the sign-in page", async ({ page }) => {
    await page.goto("/projects");

    await expect(page).toHaveURL(/\/login$/);
  });
});
