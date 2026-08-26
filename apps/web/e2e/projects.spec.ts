import { expect, test, type Page } from "@playwright/test";
import { registerAndSignIn } from "./helpers";

/** Project lifecycle and cross-user isolation, driven through the browser. */

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

    // Archiving is confirmed too: it used to fire on a single click, with no way back.
    await page.getByRole("button", { name: "Archive" }).click();
    await page.getByRole("button", { name: "Yes, archive" }).click();
    await expect(page.getByTestId("project-status")).toHaveText("Archived");

    // And it is reversible, which is what makes it archiving rather than a slow delete.
    await page.getByRole("button", { name: "Unarchive" }).click();
    await expect(page.getByTestId("project-status")).toHaveText("Draft");

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

    await expect(page.getByText("Project name is required")).toBeVisible();
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
      // Wait for the navigation to land before reading the URL. `click()` resolves as
      // soon as the click is dispatched, so reading it immediately captures /projects.
      await expect(owner).toHaveURL(/\/projects\/[0-9a-f-]{36}$/);
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
