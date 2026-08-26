import { expect, test, type Page } from "@playwright/test";
import { registerAndSignIn } from "./helpers";

/**
 * Modal confirmation and toast notifications [F-217, F-218].
 *
 * These specs exist because the interesting behaviour is the browser's, and jsdom has
 * none of it: `<dialog open>` focus containment, an inert background, Escape, and the top
 * layer are real only in a real browser. The component tests cover our own logic; this
 * covers the part we chose the platform for.
 */

async function openProjectWithDeleteDialog(page: Page, name: string): Promise<void> {
  await registerAndSignIn(page);
  await page.getByLabel("Name").fill(name);
  await page.getByRole("button", { name: "Create project" }).click();
  await page.getByRole("link", { name }).click();
  await expect(page.getByRole("heading", { name })).toBeVisible();
  await page.getByRole("button", { name: "Delete" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
}

test.describe("confirmation dialog", () => {
  test("focuses cancel rather than the destructive action", async ({ page }) => {
    // A dialog that appears with the destructive button focused turns a stray Enter into
    // a deletion.
    await openProjectWithDeleteDialog(page, "Focus Target");

    await expect(page.getByRole("button", { name: "Cancel" })).toBeFocused();
  });

  test("Escape closes it and the project survives", async ({ page }) => {
    await openProjectWithDeleteDialog(page, "Escape Hatch");

    await page.keyboard.press("Escape");

    await expect(page.getByRole("dialog")).toBeHidden();
    await expect(page.getByRole("heading", { name: "Escape Hatch" })).toBeVisible();
  });

  test("never lets focus reach the page behind it", async ({ page }) => {
    // Focus containment is the whole reason for using <dialog> over a hand-rolled overlay.
    // Tab well past the two controls it holds and record anything focus lands on outside.
    //
    // The assertion is "focus never reaches a control on the page", not "focus is always
    // inside the dialog". Chromium parks focus on <body> once per cycle — the point in the
    // sequence where browser chrome would take it — before returning to the dialog. That
    // is the browser's own step, not an escape: <body> is not operable, and the page's
    // controls (breadcrumb, Archive, Delete, Sign out) are never reached.
    await openProjectWithDeleteDialog(page, "Trapped Focus");

    const escapes: string[] = [];
    for (let i = 0; i < 8; i++) {
      await page.keyboard.press("Tab");
      const escaped = await page.evaluate(() => {
        const active = document.activeElement;
        const dialog = document.querySelector("dialog[open]");
        if (active === null || dialog === null) return null;
        if (dialog.contains(active) || active === document.body) return null;
        return `${active.tagName}: ${(active.textContent ?? "").trim().slice(0, 30)}`;
      });
      if (escaped !== null) escapes.push(escaped);
    }

    expect(escapes).toEqual([]);
  });

  test("makes the page behind unreachable", async ({ page }) => {
    // The background is inert, so a click aimed at it must not activate anything. If the
    // breadcrumb were still live, this would navigate away.
    await openProjectWithDeleteDialog(page, "Inert Background");

    await page.getByRole("link", { name: "← All projects" }).click({ force: true });

    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(page).not.toHaveURL(/\/projects$/);
  });

  test("confirming deletes and navigates away", async ({ page }) => {
    await openProjectWithDeleteDialog(page, "Goner");

    await page.getByRole("button", { name: "Yes, delete" }).click();

    await expect(page).toHaveURL(/\/projects$/);
    await expect(page.getByText("No projects yet")).toBeVisible();
  });
});

test.describe("toasts", () => {
  test("confirms a created project and then clears itself", async ({ page }) => {
    await registerAndSignIn(page);

    await page.getByLabel("Name").fill("Toasted");
    await page.getByRole("button", { name: "Create project" }).click();

    const toast = page.getByTestId("toast");
    await expect(toast).toHaveText(/Project created/);
    // It must not linger: a success that stays becomes furniture the user stops reading.
    await expect(toast).toBeHidden({ timeout: 15_000 });
  });

  test("announces a second creation as well as the first", async ({ page }) => {
    // The bug this guards: the success flag is already true after the first project, so a
    // component keyed on the flag rather than the submission announces nothing again.
    await registerAndSignIn(page);

    for (const name of ["First One", "Second One"]) {
      await page.getByLabel("Name").fill(name);
      await page.getByRole("button", { name: "Create project" }).click();
      await expect(page.getByTestId("toast")).toHaveText(/Project created/);
      await expect(page.getByRole("link", { name })).toBeVisible();
      await page.getByTestId("toast").getByRole("button").click();
    }

    await expect(page.getByTestId("project-card")).toHaveCount(2);
  });

  test("clears the form after each create", async ({ page }) => {
    // Same root cause as above, seen from the user's side.
    await registerAndSignIn(page);

    for (const name of ["Alpha", "Beta"]) {
      await page.getByLabel("Name").fill(name);
      await page.getByRole("button", { name: "Create project" }).click();
      await expect(page.getByRole("link", { name })).toBeVisible();
      await expect(page.getByLabel("Name")).toHaveValue("");
    }
  });
});
