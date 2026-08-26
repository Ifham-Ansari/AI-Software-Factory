import { expect, test, type Page } from "@playwright/test";
import { registerAndSignIn } from "./helpers";

/**
 * Archiving, unarchiving and finding what was archived [F-220].
 *
 * Archiving used to fire on one click with no way back, which made it indistinguishable
 * from a delete that took a moment longer to notice. These cover the round trip and,
 * just as importantly, that an archived project can still be found.
 */

async function createAndOpen(page: Page, name: string): Promise<void> {
  await page.getByLabel("Name").fill(name);
  await page.getByRole("button", { name: "Create project" }).click();
  await page.getByRole("link", { name }).click();
  await expect(page.getByRole("heading", { name })).toBeVisible();
}

async function archive(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Archive" }).click();
  await page.getByRole("button", { name: "Yes, archive" }).click();
  await expect(page.getByTestId("project-status")).toHaveText("Archived");
}

test.describe("archiving", () => {
  test("asks before archiving, and can be called off", async ({ page }) => {
    await registerAndSignIn(page);
    await createAndOpen(page, "Second Thoughts");

    await page.getByRole("button", { name: "Archive" }).click();
    await page.getByRole("button", { name: "Cancel" }).click();

    await expect(page.getByRole("dialog")).toBeHidden();
    await expect(page.getByTestId("project-status")).toHaveText("Draft");
  });

  test("archives and unarchives, leaving the project writable again", async ({ page }) => {
    await registerAndSignIn(page);
    await createAndOpen(page, "Round Trip");
    await archive(page);

    await page.getByRole("button", { name: "Unarchive" }).click();

    await expect(page.getByTestId("project-status")).toHaveText("Draft");
    // The Archive control returning is the visible proof the project accepts changes
    // again — an archived one is read-only and offers no such option.
    await expect(page.getByRole("button", { name: "Archive" })).toBeVisible();
  });

  test("an archived project is still listed and still reachable", async ({ page }) => {
    // The failure this guards against: archive something and it appears to be gone.
    await registerAndSignIn(page);
    await createAndOpen(page, "Filed Away");
    await archive(page);

    await page.getByRole("link", { name: "← All projects" }).click();

    await expect(page.getByRole("link", { name: "Filed Away" })).toBeVisible();
    await expect(page.getByTestId("project-status")).toHaveText("Archived");
  });

  test("filters the list down to archived projects", async ({ page }) => {
    await registerAndSignIn(page);
    await createAndOpen(page, "Kept Active");
    await page.getByRole("link", { name: "← All projects" }).click();
    await createAndOpen(page, "Put Away");
    await archive(page);
    await page.getByRole("link", { name: "← All projects" }).click();

    await page.getByRole("link", { name: "Archived" }).click();

    await expect(page.getByRole("link", { name: "Put Away" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Kept Active" })).toBeHidden();

    await page.getByRole("link", { name: "Active", exact: true }).click();

    await expect(page.getByRole("link", { name: "Kept Active" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Put Away" })).toBeHidden();
  });
});
