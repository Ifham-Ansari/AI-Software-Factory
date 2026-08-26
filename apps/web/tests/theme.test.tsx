import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ThemeToggle } from "@/components/ui";
import {
  DEFAULT_THEME,
  THEME_INIT_SCRIPT,
  THEME_STORAGE_KEY,
  applyTheme,
  isTheme,
  readTheme,
  subscribeToTheme,
} from "@/lib/theme/theme";

/**
 * Colour theme [F-219].
 *
 * Two explicit themes and no system option, so the assertions are about the stored choice
 * being honoured — including when storage refuses to cooperate, which is a normal state
 * in a private window rather than an exotic failure.
 */


/**
 * An in-memory `localStorage`.
 *
 * Stubbed rather than used from the environment: Node now ships its own experimental
 * `localStorage` which shadows jsdom's and implements only part of the interface, so
 * whether `clear()` exists depends on the runtime rather than on anything we control.
 * A stub makes these tests independent of that, and lets the "storage refuses" cases be
 * expressed directly instead of by monkey-patching a prototype that may be frozen.
 */
function stubStorage(options: { throwOnGet?: boolean; throwOnSet?: boolean } = {}) {
  const entries = new Map<string, string>();
  const storage = {
    getItem(key: string): string | null {
      if (options.throwOnGet) throw new Error("storage blocked");
      return entries.get(key) ?? null;
    },
    setItem(key: string, value: string): void {
      if (options.throwOnSet) throw new Error("QuotaExceededError");
      entries.set(key, value);
    },
    removeItem(key: string): void {
      entries.delete(key);
    },
    clear(): void {
      entries.clear();
    },
  };
  vi.stubGlobal("localStorage", storage);
  return storage;
}

describe("theme module", () => {
  beforeEach(() => {
    document.documentElement.removeAttribute("data-theme");
    stubStorage();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("falls back to the default when nothing is applied", () => {
    expect(readTheme()).toBe(DEFAULT_THEME);
  });

  it("reads the theme applied to the document", () => {
    document.documentElement.dataset.theme = "light";

    expect(readTheme()).toBe("light");
  });

  it("ignores a stored value that is not a theme", () => {
    // The stored value is user-writable, so it is validated rather than trusted.
    document.documentElement.dataset.theme = "chartreuse";

    expect(readTheme()).toBe(DEFAULT_THEME);
    expect(isTheme("chartreuse")).toBe(false);
  });

  it("applies and remembers a theme", () => {
    applyTheme("light");

    expect(document.documentElement.dataset.theme).toBe("light");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
  });

  it("still applies the theme when storage refuses", () => {
    // A private window can throw on setItem. Losing the preference for next time is
    // acceptable; refusing to switch at all is not.
    stubStorage({ throwOnSet: true });

    expect(() => applyTheme("light")).not.toThrow();
    expect(document.documentElement.dataset.theme).toBe("light");
  });
});

describe("cross-tab sync", () => {
  beforeEach(() => {
    document.documentElement.dataset.theme = "dark";
    stubStorage();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("adopts a theme chosen in another tab", () => {
    // Two windows of the same app showing different themes is a bug people notice
    // immediately, and the storage event is the only signal we get.
    const unsubscribe = subscribeToTheme(() => undefined);

    window.dispatchEvent(
      new StorageEvent("storage", { key: THEME_STORAGE_KEY, newValue: "light" }),
    );

    expect(document.documentElement.dataset.theme).toBe("light");
    unsubscribe();
  });

  it("ignores storage events for other keys", () => {
    const unsubscribe = subscribeToTheme(() => undefined);

    window.dispatchEvent(
      new StorageEvent("storage", { key: "something-else", newValue: "light" }),
    );

    expect(document.documentElement.dataset.theme).toBe("dark");
    unsubscribe();
  });

  it("ignores a junk value from another tab", () => {
    const unsubscribe = subscribeToTheme(() => undefined);

    window.dispatchEvent(
      new StorageEvent("storage", { key: THEME_STORAGE_KEY, newValue: "neon" }),
    );

    expect(document.documentElement.dataset.theme).toBe("dark");
    unsubscribe();
  });

  it("stops listening once unsubscribed", () => {
    const unsubscribe = subscribeToTheme(() => undefined);
    unsubscribe();

    window.dispatchEvent(
      new StorageEvent("storage", { key: THEME_STORAGE_KEY, newValue: "light" }),
    );

    expect(document.documentElement.dataset.theme).toBe("dark");
  });
});

describe("the pre-paint script", () => {
  beforeEach(() => {
    document.documentElement.removeAttribute("data-theme");
    stubStorage();
  });
  afterEach(() => vi.unstubAllGlobals());

  /** Run it the way the browser would, rather than asserting on its source text. */
  const runInitScript = () => new Function(THEME_INIT_SCRIPT)();

  it("applies the stored theme", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "light");

    runInitScript();

    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("applies the default when nothing is stored", () => {
    runInitScript();

    expect(document.documentElement.dataset.theme).toBe(DEFAULT_THEME);
  });

  it("applies the default when the stored value is junk", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "neon");

    runInitScript();

    expect(document.documentElement.dataset.theme).toBe(DEFAULT_THEME);
  });

  it("still sets a theme when storage throws", () => {
    // Without the catch, a throw here aborts the rest of <head>.
    stubStorage({ throwOnGet: true });

    expect(() => runInitScript()).not.toThrow();
    expect(document.documentElement.dataset.theme).toBe(DEFAULT_THEME);
  });
});

describe("ThemeToggle", () => {
  beforeEach(() => {
    document.documentElement.dataset.theme = "dark";
    stubStorage();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("switches to the other theme and back", () => {
    render(<ThemeToggle />);
    const button = screen.getByTestId("theme-toggle");

    fireEvent.click(button);
    expect(document.documentElement.dataset.theme).toBe("light");

    fireEvent.click(button);
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("names the theme it will switch to", () => {
    render(<ThemeToggle />);

    expect(screen.getByTestId("theme-toggle")).toHaveAccessibleName("Switch to light theme");
  });

  it("renders identical markup in both themes", () => {
    // The toggle's appearance is driven by CSS from html[data-theme], so the HTML never
    // depends on the applied theme. That is what keeps it from being a guaranteed
    // hydration mismatch for anyone not using the default.
    const dark = render(<ThemeToggle />).container.innerHTML;
    document.documentElement.dataset.theme = "light";
    const light = render(<ThemeToggle />).container.innerHTML;

    expect(dark.replace(/light/g, "dark")).toBe(light.replace(/light/g, "dark"));
  });
});
