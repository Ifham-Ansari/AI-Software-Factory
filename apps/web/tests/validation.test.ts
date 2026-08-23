import { describe, expect, it } from "vitest";
import {
  createProjectSchema,
  fieldErrors,
  registerSchema,
  signInSchema,
  MIN_PASSWORD_LENGTH,
} from "@/lib/validation";

/**
 * Client-side validation mirrors the backend's rules so users get immediate feedback.
 * It is a convenience, never a control — the backend validates everything again.
 */
describe("registerSchema", () => {
  it("accepts a valid registration", () => {
    const result = registerSchema.safeParse({
      email: "ada@example.com",
      password: "a-sufficiently-long-passphrase",
      display_name: "Ada Lovelace",
    });

    expect(result.success).toBe(true);
  });

  it.each([
    ["not-an-email", "email"],
    ["", "email"],
    ["a@", "email"],
  ])("rejects invalid email %s", (email, field) => {
    const result = registerSchema.safeParse({
      email,
      password: "a-sufficiently-long-passphrase",
      display_name: "Ada",
    });

    expect(result.success).toBe(false);
    if (!result.success) {
      expect(Object.keys(fieldErrors(result.error))).toContain(field);
    }
  });

  it("enforces the minimum password length", () => {
    const result = registerSchema.safeParse({
      email: "ada@example.com",
      password: "x".repeat(MIN_PASSWORD_LENGTH - 1),
      display_name: "Ada",
    });

    expect(result.success).toBe(false);
  });

  it("rejects a blank display name", () => {
    const result = registerSchema.safeParse({
      email: "ada@example.com",
      password: "a-sufficiently-long-passphrase",
      display_name: "   ",
    });

    expect(result.success).toBe(false);
  });
});

describe("signInSchema", () => {
  it("does not impose a minimum password length", () => {
    // Rejecting a short password here would reveal that the stored one is longer, and an
    // older account must still be able to sign in.
    const result = signInSchema.safeParse({ email: "ada@example.com", password: "x" });

    expect(result.success).toBe(true);
  });

  it("still requires a password", () => {
    const result = signInSchema.safeParse({ email: "ada@example.com", password: "" });

    expect(result.success).toBe(false);
  });
});

describe("createProjectSchema", () => {
  it("trims whitespace", () => {
    const result = createProjectSchema.safeParse({ name: "  Spaced  ", description: "" });

    expect(result.success && result.data.name).toBe("Spaced");
  });

  it("rejects a whitespace-only name", () => {
    const result = createProjectSchema.safeParse({ name: "   " });

    expect(result.success).toBe(false);
  });

  it("defaults an omitted description to empty", () => {
    const result = createProjectSchema.safeParse({ name: "Valid" });

    expect(result.success && result.data.description).toBe("");
  });

  it("rejects a name over the limit", () => {
    const result = createProjectSchema.safeParse({ name: "x".repeat(121) });

    expect(result.success).toBe(false);
  });
});

describe("fieldErrors", () => {
  it("keys messages by field and keeps the first per field", () => {
    const result = registerSchema.safeParse({ email: "bad", password: "s", display_name: "" });

    expect(result.success).toBe(false);
    if (!result.success) {
      const errors = fieldErrors(result.error);
      expect(errors).toHaveProperty("email");
      expect(errors).toHaveProperty("password");
      expect(typeof errors.email).toBe("string");
    }
  });
});
