"use client";

import { useSyncExternalStore } from "react";
import {
  DEFAULT_THEME,
  applyTheme,
  readTheme,
  subscribeToTheme,
  type Theme,
} from "@/lib/theme/theme";

/**
 * Switch between the two themes [F-219].
 *
 * **The markup is identical in both themes**, and that is deliberate. The applied theme
 * comes from `localStorage` via the head script, which the server cannot know, so any
 * theme-dependent text or icon in the HTML would be a guaranteed hydration mismatch on
 * every load for anyone not using the default. Instead the icon is drawn by CSS from
 * `html[data-theme]`, and only the accessible name — which is not compared during
 * hydration in a way that breaks the tree — names the destination.
 *
 * `useSyncExternalStore` rather than `useState` + `useEffect`: the theme genuinely lives
 * outside React, on the `<html>` element, put there before React loaded. Copying it into
 * component state after mount would render once with the wrong value and re-render, and
 * would miss changes made from another tab.
 */
export function ThemeToggle() {
  const theme = useSyncExternalStore<Theme>(
    subscribeToTheme,
    readTheme,
    // On the server there is no document; the head script has not run yet either, so the
    // default is the only honest answer.
    () => DEFAULT_THEME,
  );
  const next: Theme = theme === "dark" ? "light" : "dark";

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={() => applyTheme(next)}
      aria-label={`Switch to ${next} theme`}
      data-testid="theme-toggle"
    >
      <span className="theme-toggle-icon" aria-hidden="true" />
    </button>
  );
}
