import { expect, test, type Page } from "@playwright/test";

/** Project lifecycle and cross-user isolation, driven through the browser. */

function uniqueEmail(): string {
  return `e2e-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.test`;
}

const PASSWORD = "an-e2e-passphrase-long-enough";

async function registerAndSignIn(page: Page, name = "E2E User"): Promise<void> {
  await page.goto("/register");
  await page.getByLabel("Name").fill(name);
  await page.getByLabel("Email").fill(uniqueEmail());
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/projects$/);
}

async function createProject(page: Page, name: string): Promise<void> {
  await page.getByLabel("Name").fill(name);
  await page.getByRole("button", { name: "Create project" }).click();
  await expect(page.getByRole("link", { name })).toBeVisible();
}

test.describe("project lifecycle", () => {
  test("create, open, archive and delete", async ({ page }) => {
    await registerAndSignIn(page);
    await createProject(page, "Lifecycle Project");

    await page.getByRole("link", { name: "Lifecycle Project" }).click();
    await expect(page.getByRole("heading", { name: "Lifecycle Project" })).toBeVisible();
    await expect(page.getByTestId("project-status")).toHaveText("Draft");

    await page.getByRole("button", { name: "Archive" }).click();
    await expect(page.getByTestId("project-status")).toHaveText("Archived");

    // Deletion is confirmed, not immediate.
    await page.getByRole("button", { name: "Delete" }).click();
    await expect(page.getByText("Delete this project permanently?")).toBeVisible();
    await page.getByRole("button", { name: "Yes, delete" }).click();

    await expect(page).toHaveURL(/\/projects$/);
    await expect(page.getByText("No projects yet")).toBeVisible();
  });

  test("deletion can be cancelled", async ({ page }) => {
    await registerAndSignIn(page);
    await createProject(page, "Keep Me");

    await page.getByRole("link", { name: "Keep Me" }).click();
    await page.getByRole("button", { name: "Delete" }).click();
    await page.getByRole("button", { name: "Cancel" }).click();

    await expect(page.getByText("Delete this project permanently?")).not.toBeVisible();
    await expect(page.getByRole("heading", { name: "Keep Me" })).toBeVisible();
  });

  test("two projects with the same name get distinct slugs", async ({ page }) => {
    await registerAndSignIn(page);

    await createProject(page, "Inventory");
    await page.getByLabel("Name").fill("Inventory");
    await page.getByRole("button", { name: "Create project" }).click();

    await expect(page.getByTestId("project-card")).toHaveCount(2);
    await expect(page.getByText("inventory-2")).toBeVisible();
  });

  test("rejects a blank project name", async ({ page }) => {
    await registerAndSignIn(page);

    await page.getByLabel("Name").fill("   ");
    await page.getByRole("button", { name: "Create project" }).click();

    await expect(page.getByRole("alert").first()).toBeVisible();
    await expect(page.getByTestId("project-card")).toHaveCount(0);
  });
});

test.describe("isolation", () => {
  test("one user cannot see or reach another user's project", async ({ browser }) => {
    // Two isolated browser contexts, so the two users have separate cookie jars.
    const ownerContext = await browser.newContext();
    const strangerContext = await browser.newContext();
    const owner = await ownerContext.newPage();
    const stranger = await strangerContext.newPage();

    try {
      await registerAndSignIn(owner, "Owner");
      await createProject(owner, "Private Project");
      await owner.getByRole("link", { name: "Private Project" }).click();
      const projectUrl = owner.url();

      await registerAndSignIn(stranger, "Stranger");

      // The stranger's list is empty despite the owner having a project.
      await expect(stranger.getByText("No projects yet")).toBeVisible();

      // And the direct URL is a 404, not a 403: a 403 would confirm the id is real.
      await stranger.goto(projectUrl);
      await expect(stranger.getByText("Not found")).toBeVisible();
    } finally {
      await ownerContext.close();
      await strangerContext.close();
    }
  });
});
