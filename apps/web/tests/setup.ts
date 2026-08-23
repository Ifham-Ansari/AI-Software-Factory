/**
 * Vitest setup.
 *
 * Adds jest-dom matchers and clears the DOM between tests, so a component left mounted by
 * one test cannot be found by the next and produce a false pass.
 */

import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
});
