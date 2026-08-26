/**
 * Vitest setup.
 *
 * Adds jest-dom matchers and clears the DOM between tests, so a component left mounted by
 * one test cannot be found by the next and produce a false pass.
 */

import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

/**
 * Minimal `<dialog>` support for jsdom.
 *
 * jsdom 25 parses `<dialog>` but implements none of its behaviour — `showModal` and
 * `close` are simply absent, so any component using them throws on render. This models
 * just the contract our code depends on: the `open` property tracks visibility, and
 * `close()` fires a `close` event.
 *
 * It deliberately does **not** fake the parts that make the real element worth using —
 * focus containment, the inert background, Escape handling, the top layer. Those are
 * browser behaviour, a polyfill of them here would only be asserting against itself, and
 * they are covered where they are real: the Playwright suite.
 */
function installDialogPolyfill(): void {
  const proto = globalThis.HTMLDialogElement?.prototype;
  if (proto === undefined || typeof proto.showModal === "function") return;

  proto.showModal = function showModal(this: HTMLDialogElement): void {
    this.open = true;
  };
  proto.show = function show(this: HTMLDialogElement): void {
    this.open = true;
  };
  proto.close = function close(this: HTMLDialogElement, returnValue?: string): void {
    if (!this.open) return;
    this.open = false;
    if (returnValue !== undefined) this.returnValue = returnValue;
    this.dispatchEvent(new Event("close"));
  };
}

installDialogPolyfill();

afterEach(() => {
  cleanup();
});
