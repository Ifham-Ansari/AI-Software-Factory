import { expect, test, type Page } from "@playwright/test";
import { registerAndSignIn } from "./helpers";

/**
 * Archiving, unarchiving and finding what was archived [F-220].
 *
 * Archiving used to fire on one click with no way back, which made it indistinguishable
 * from a delete that took a moment longer to notice. These cover the round trip and,
 * just as importantly, that an archived project can still be found.
 *
 * Both directions are confirmed. Unarchiving is reversible, but it is still a state change
 * the user may not have meant, and it occupies the same position on the row that Archive
 * did — so the click that reaches it is exactly the one aimed at something else.
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

async function unarchive(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Unarchive" }).click();
  await page.getByRole("button", { name: "Yes, unarchive" }).click();
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

    await unarchive(page);

    await expect(page.getByTestId("project-status")).toHaveText("Draft");
    // The Archive and Edit controls returning are the visible proof the project accepts
    // changes again — an archived one is read-only and offers neither.
    await expect(page.getByRole("button", { name: "Archive" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Edit" })).toBeVisible();
  });

  test("asks before unarchiving, and can be called off", async ({ page }) => {
    await registerAndSignIn(page);
    await createAndOpen(page, "Stays Filed");
    await archive(page);

    await page.getByRole("button", { name: "Unarchive" }).click();
    await expect(page.getByText("Unarchive this project?")).toBeVisible();
    await page.getByRole("button", { name: "Cancel" }).click();

    await expect(page.getByRole("dialog")).toBeHidden();
    // Cancel leaves the project exactly as it was, on the page and on the server.
    await expect(page.getByTestId("project-status")).toHaveText("Archived");
    await page.reload();
    await expect(page.getByTestId("project-status")).toHaveText("Archived");
  });

  test("leaves no second trigger behind once it has run", async ({ page }) => {
    // Confirming is the only way to fire the action, and the dialog carrying that button
    // closes on success — so there is nothing left to click a second time. That the button
    // is also disabled *during* the request is asserted in the component suite, where the
    // pending state can be held still rather than raced against.
    await registerAndSignIn(page);
    await createAndOpen(page, "One Request Only");
    await archive(page);

    await page.getByRole("button", { name: "Unarchive" }).click();
    const confirm = page.getByRole("button", { name: "Yes, unarchive" });
    await confirm.click();

    await expect(page.getByTestId("project-status")).toHaveText("Draft");
    await expect(confirm).toBeHidden();
  });

  test("an archived project offers no way to edit it", async ({ page }) => {
    // Archived means read-only, and the backend refuses the write. Offering the control
    // anyway would be an invitation to a 403.
    await registerAndSignIn(page);
    await createAndOpen(page, "Read Only");
    await archive(page);

    await expect(page.getByRole("button", { name: "Edit" })).toBeHidden();
    await expect(page.getByRole("button", { name: "Archive", exact: true })).toBeHidden();
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
