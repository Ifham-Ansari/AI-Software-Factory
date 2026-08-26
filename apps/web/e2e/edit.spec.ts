import { expect, test, type Page } from "@playwright/test";
import { registerAndSignIn } from "./helpers";

/**
 * Editing a project [F-221].
 *
 * Its own file, alongside `archive.spec.ts`, because the suite is organised per feature and
 * because the interesting cases here are all about what the *form* does between openings —
 * which is a different subject from the lifecycle transitions next door.
 */

async function createProject(page: Page, name: string): Promise<void> {
  await page.getByLabel("Name").fill(name);
  await page.getByRole("button", { name: "Create project" }).click();
  await expect(page.getByRole("link", { name })).toBeVisible();
}

test.describe("editing a project", () => {
  test("renames a project, and the change persists", async ({ page }) => {
    await registerAndSignIn(page);
    await createProject(page, "Working Title");
    await page.getByRole("link", { name: "Working Title" }).click();

    await page.getByRole("button", { name: "Edit" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    // The form opens holding what the project currently is, not an empty box.
    await expect(page.getByLabel("Name")).toHaveValue("Working Title");

    await page.getByLabel("Name").fill("Final Title");
    await page.getByLabel("Description").fill("Now it says what it does.");
    await page.getByRole("button", { name: "Save changes" }).click();

    await expect(page.getByRole("dialog")).toBeHidden();
    await expect(page.getByRole("heading", { name: "Final Title" })).toBeVisible();
    // Scoped to the rendered paragraph: the edit dialog stays mounted while closed and its
    // textarea still holds the same text, which would otherwise match twice.
    await expect(page.locator("p.project-description")).toHaveText("Now it says what it does.");

    // Persisted, not merely re-rendered.
    await page.reload();
    await expect(page.getByRole("heading", { name: "Final Title" })).toBeVisible();
  });

  test("rejects a blank name inline, and changes nothing", async ({ page }) => {
    await registerAndSignIn(page);
    await createProject(page, "Keeps Its Name");
    await page.getByRole("link", { name: "Keeps Its Name" }).click();

    await page.getByRole("button", { name: "Edit" }).click();
    await page.getByLabel("Name").fill("   ");
    await page.getByRole("button", { name: "Save changes" }).click();

    // The message belongs beside the field, and the dialog stays open holding the edit.
    await expect(page.getByText("Project name is required")).toBeVisible();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(page.getByRole("heading", { name: "Keeps Its Name" })).toBeVisible();
  });

  test("a rejected save keeps what was typed", async ({ page }) => {
    // React resets an uncontrolled form once its action completes, failure included. Left
    // alone, the form throws away the text at the exact moment it asks the user to correct
    // it — including the field that was fine, which they then have to retype.
    //
    // The rejection used here is a blanked name, because it is the only one this form can
    // actually produce: the name input carries `maxLength`, so an over-long name is
    // truncated by the browser and never reaches validation at all.
    await registerAndSignIn(page);
    await createProject(page, "Nearly Right");
    await page.getByRole("link", { name: "Nearly Right" }).click();

    await page.getByRole("button", { name: "Edit" }).click();
    await page.getByLabel("Name").fill("   ");
    await page.getByLabel("Description").fill("Worth keeping.");
    await page.getByRole("button", { name: "Save changes" }).click();

    await expect(page.getByText("Project name is required")).toBeVisible();
    await expect(page.getByLabel("Name")).toHaveValue("   ");
    await expect(page.getByLabel("Description")).toHaveValue("Worth keeping.");

    // And correcting it from there saves, rather than needing the dialog reopened.
    await page.getByLabel("Name").fill("Exactly Right");
    await page.getByRole("button", { name: "Save changes" }).click();

    await expect(page.getByRole("dialog")).toBeHidden();
    await expect(page.getByRole("heading", { name: "Exactly Right" })).toBeVisible();
    await expect(page.locator("p.project-description")).toHaveText("Worth keeping.");
  });

  test("cancelling discards the edit, including on a second open", async ({ page }) => {
    // The dialog stays mounted while closed so the browser can animate it, which is what
    // makes an abandoned edit able to survive into the next open if nothing resets it.
    await registerAndSignIn(page);
    await createProject(page, "Unchanged");
    await page.getByRole("link", { name: "Unchanged" }).click();

    await page.getByRole("button", { name: "Edit" }).click();
    await page.getByLabel("Name").fill("Typed Then Abandoned");
    await page.getByRole("button", { name: "Cancel" }).click();

    await expect(page.getByRole("heading", { name: "Unchanged" })).toBeVisible();
    await page.getByRole("button", { name: "Edit" }).click();
    await expect(page.getByLabel("Name")).toHaveValue("Unchanged");

    // An *abandoned rejection* has to clear as well. That state — a failed attempt whose
    // values the form is deliberately holding on to — is the one a remount per opening
    // exists to discard, and the one that would otherwise reappear here.
    await page.getByLabel("Name").fill("   ");
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByText("Project name is required")).toBeVisible();
    await page.getByRole("button", { name: "Cancel" }).click();

    await page.getByRole("button", { name: "Edit" }).click();
    await expect(page.getByLabel("Name")).toHaveValue("Unchanged");
    await expect(page.getByText("Project name is required")).toBeHidden();
  });

  test("clears a description by emptying the field", async ({ page }) => {
    await registerAndSignIn(page);
    await page.getByLabel("Name").fill("Has A Description");
    await page.getByLabel("Description").fill("Delete me.");
    await page.getByRole("button", { name: "Create project" }).click();
    await page.getByRole("link", { name: "Has A Description" }).click();
    await expect(page.locator("p.project-description")).toHaveText("Delete me.");

    await page.getByRole("button", { name: "Edit" }).click();
    await page.getByLabel("Description").fill("");
    await page.getByRole("button", { name: "Save changes" }).click();

    await expect(page.getByRole("dialog")).toBeHidden();
    await expect(page.locator("p.project-description")).toHaveText("No description yet.");
  });
});
