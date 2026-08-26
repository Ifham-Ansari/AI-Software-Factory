import { expect, test, type Page } from "@playwright/test";
import { registerAndSignIn } from "./helpers";

/**
 * Colour theme [F-219].
 *
 * Two themes chosen explicitly, with no system option. The property worth proving in a
 * real browser is the one unit tests cannot reach: that the stored choice is applied
 * before the first paint, so a reload does not flash the wrong theme.
 */

/** The theme attribute present in the very first HTML the browser parses. */
async function themeBeforeHydration(page: Page): Promise<string | null> {
  return page.evaluate(() => document.documentElement.dataset.theme ?? null);
}


test.describe("theme", () => {
  test("defaults to dark and switches to light", async ({ page }) => {
    await page.goto("/login");

    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

    await page.getByTestId("theme-toggle").click();

    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  });

  test("remembers the choice across a reload, with no flash of the wrong theme", async ({
    page,
  }) => {
    // The reason the theme is applied by a blocking script in <head> rather than by React:
    // anything that runs after hydration paints one frame of the previous theme first.
    await page.goto("/login");
    await page.getByTestId("theme-toggle").click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");

    await page.reload();

    // Read as early as the browser will let us: if the theme were applied during
    // hydration this would still say "dark".
    expect(await themeBeforeHydration(page)).toBe("light");
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  });

  test("carries the choice into the signed-in app", async ({ page }) => {
    await page.goto("/login");
    await page.getByTestId("theme-toggle").click();

    await registerAndSignIn(page);

    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    await expect(page.getByTestId("theme-toggle")).toBeVisible();
  });

  test("ignores a stored value that is not a theme", async ({ page }) => {
    // The stored value is user-writable, so a junk value must fall back rather than leave
    // the page with no theme at all.
    await page.goto("/login");
    await page.evaluate(() => localStorage.setItem("factory-theme", "neon"));

    await page.reload();

    expect(await themeBeforeHydration(page)).toBe("dark");
  });
});
