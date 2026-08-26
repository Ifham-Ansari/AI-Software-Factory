/**
 * Colour theme [F-219].
 *
 * Two themes, chosen explicitly: dark and light. There is deliberately no "system" option
 * and no `prefers-color-scheme` anywhere in the stylesheet — the setting is the user's
 * choice, stored, and honoured until they change it.
 */

export type Theme = "dark" | "light";

export const THEMES: readonly Theme[] = ["dark", "light"];

/** The theme a first-time visitor gets. */
export const DEFAULT_THEME: Theme = "dark";

export const THEME_STORAGE_KEY = "factory-theme";

export function isTheme(value: unknown): value is Theme {
  return value === "dark" || value === "light";
}

/**
 * The script that applies the stored theme before the first paint.
 *
 * This has to run **synchronously in `<head>`**, before the browser paints anything. React
 * cannot do it: the server has no access to `localStorage`, so any theme applied during
 * hydration arrives after a frame of the wrong colours — the "flash of incorrect theme"
 * that makes a theme toggle feel broken every time the page loads.
 *
 * It is kept to one statement, with its own try/catch, because a throw here (a browser
 * with site data blocked, a private window) would abort the rest of the document's head.
 * Any failure falls back to the default rather than leaving the attribute unset, which
 * would leave the page unstyled-looking until hydration.
 */
export const THEME_INIT_SCRIPT = `(function(){try{var t=localStorage.getItem(${JSON.stringify(
  THEME_STORAGE_KEY,
)});document.documentElement.dataset.theme=(t==="dark"||t==="light")?t:${JSON.stringify(
  DEFAULT_THEME,
)}}catch(e){document.documentElement.dataset.theme=${JSON.stringify(DEFAULT_THEME)}}})()`;

/** Read the theme currently applied to the document. */
export function readTheme(): Theme {
  if (typeof document === "undefined") return DEFAULT_THEME;
  const applied = document.documentElement.dataset.theme;
  return isTheme(applied) ? applied : DEFAULT_THEME;
}

/**
 * Apply a theme and remember it.
 *
 * Storage is best-effort: a browser that refuses it still gets the theme for this page,
 * which is better than refusing to switch at all.
 */
export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // Private mode, or site data blocked. The choice holds for this page and is forgotten
    // on the next, which is the most this browser will allow.
  }
  for (const listener of listeners) listener();
}

/**
 * The applied theme is state owned outside React — an attribute on `<html>`, written
 * before React exists by the head script and readable by any tab. These make it an
 * external store React can subscribe to properly, rather than something copied into
 * component state by an effect that runs a render too late.
 */
const listeners = new Set<() => void>();

/** Subscribe to theme changes, including ones made in another tab. */
export function subscribeToTheme(listener: () => void): () => void {
  listeners.add(listener);
  const onStorage = (event: StorageEvent) => {
    // Another tab changed the preference. Apply it here too, so a theme switch does not
    // leave a second window of the same app in the other one.
    if (event.key !== THEME_STORAGE_KEY || !isTheme(event.newValue)) return;
    document.documentElement.dataset.theme = event.newValue;
    listener();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}
