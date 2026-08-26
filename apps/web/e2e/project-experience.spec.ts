import { expect, test, type Page } from "@playwright/test";
import { registerAndSignIn } from "./helpers";

/**
 * The project experience: motion, and focus parity [F-222].
 *
 * Both properties are real only in a browser. jsdom evaluates no CSS at all — the Vitest
 * config sets `css: false` — so a component test asserting either one would be asserting
 * nothing. These read computed style from a rendered page instead.
 */

async function createProject(page: Page, name: string): Promise<void> {
  await page.getByLabel("Name").fill(name);
  await page.getByRole("button", { name: "Create project" }).click();
  await expect(page.getByRole("link", { name })).toBeVisible();
}

/** The animation the first project card is actually running, per the browser. */
function cardAnimation(page: Page): Promise<string> {
  return page
    .getByTestId("project-card")
    .first()
    .evaluate((node) => getComputedStyle(node).animationName);
}

test.describe("project list motion", () => {
  test("animates the list in, and drops it entirely under reduced motion", async ({ page }) => {
    // The rule being proved is that entrance motion is *declared inside*
    // `prefers-reduced-motion: no-preference`, not switched off afterwards. Written the
    // other way round the animation still runs — at 0.01ms, but running — and every
    // animation added later is live for everyone until someone remembers to exclude it.
    //
    // Emulated per-page rather than through `test.use`, so the two halves of the claim are
    // asserted against one rendered list and the comparison cannot drift.
    await registerAndSignIn(page);
    await createProject(page, "Moving In");

    await page.emulateMedia({ reducedMotion: "no-preference" });
    expect(await cardAnimation(page)).toBe("rise-in");

    await page.emulateMedia({ reducedMotion: "reduce" });
    expect(await cardAnimation(page)).toBe("none");
  });
});

test.describe("focus parity", () => {
  test("a card focused by keyboard is marked like a card under the pointer", async ({
    page,
  }) => {
    // Without `:focus-within` the card a keyboard user has tabbed to is the only one on the
    // page giving no indication that it is the one they are on.
    await registerAndSignIn(page);
    await createProject(page, "Tabbed To");

    const card = page.getByTestId("project-card").first();
    const borderColor = () => card.evaluate((node) => getComputedStyle(node).borderTopColor);
    // Resolved through the browser so the expectation is the token, not a hard-coded hex
    // that a theme change would quietly invalidate.
    const accent = await page.evaluate(() => {
      const probe = document.createElement("span");
      probe.style.color = getComputedStyle(document.documentElement).getPropertyValue("--accent");
      document.body.append(probe);
      const resolved = getComputedStyle(probe).color;
      probe.remove();
      return resolved;
    });

    const resting = await borderColor();
    expect(resting).not.toBe(accent);

    // Polled, not read once: the border is transitioned, so an immediate read catches a
    // colour part-way between the two and proves nothing about where it lands.
    await page.getByRole("link", { name: "Tabbed To" }).focus();
    await expect.poll(borderColor).toBe(accent);

    await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
    await expect.poll(borderColor).toBe(resting);

    await card.hover();
    await expect.poll(borderColor).toBe(accent);
  });
});
