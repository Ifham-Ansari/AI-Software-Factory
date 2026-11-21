import { describe, expect, it } from "vitest";
import { normalizeBatch } from "./batch.ts";

describe("question batches in other shapes", () => {
  it("keeps the documented shape as it is", () => {
    const b = {
      intro: "One decision.",
      questions: [{ id: "Q1", topic: "Users", question: "Who uses it?", options: [{ key: "A", label: "Only you" }, { key: "B", label: "Staff" }], recommended: "A", why_it_matters: "Roles." }],
    };
    expect(normalizeBatch(b)).toEqual(b);
  });

  it("reads options as {label, value} with the recommendation by value (a free model's discovery batch)", () => {
    const b = normalizeBatch({
      questions: [
        {
          id: "q1",
          question: "Who is the primary audience?",
          options: [
            { label: "Customers (public-facing booking site)", value: "customers" },
            { label: "Salon staff", value: "staff" },
          ],
          recommended: "customers",
          why: "Changes the architecture.",
        },
      ],
    });
    expect(b.questions[0]).toEqual({
      id: "q1",
      question: "Who is the primary audience?",
      options: [
        { key: "customers", label: "Customers (public-facing booking site)" },
        { key: "staff", label: "Salon staff" },
      ],
      recommended: "customers",
      why_it_matters: "Changes the architecture.",
    });
  });

  it("reads options as a map and a recommendation sentence (a free model's design directions)", () => {
    const b = normalizeBatch({
      questions: [
        {
          id: "design-direction",
          question: "Choose the visual direction.",
          options: { A: "A — Ledger: calm and precise.", B: "B — Atelier: dark and moody.", C: "C — Bloom: soft and modern." },
          recommendation: "C — Bloom. The dual-accent system separates hair from nails.",
        },
      ],
    });
    expect(b.questions[0]).toEqual({
      id: "design-direction",
      question: "Choose the visual direction.",
      options: [
        { key: "A", label: "Ledger: calm and precise." },
        { key: "B", label: "Atelier: dark and moody." },
        { key: "C", label: "Bloom: soft and modern." },
      ],
      recommended: "C",
      why_it_matters: "The dual-accent system separates hair from nails.",
    });
  });

  it("copes with plain strings, missing ids, and junk", () => {
    const b = normalizeBatch({ questions: [{ text: "Which stack?", choices: ["Next.js", "Vue"], recommended: "Vue" }, "Anything else?", null, 42, { id: "x" }] });
    expect(b.questions).toEqual([
      { id: "Q1", question: "Which stack?", options: [{ key: "A", label: "Next.js" }, { key: "B", label: "Vue" }], recommended: "B" },
      { id: "Q2", question: "Anything else?" },
    ]);
    expect(normalizeBatch("nonsense").questions).toEqual([]);
    expect(normalizeBatch([{ id: "a", question: "A list at the top level?" }]).questions).toHaveLength(1);
  });

  it("does not read a sentence that merely starts with a letter as that option", () => {
    const b = normalizeBatch({ questions: [{ id: "q", question: "Pick", options: { A: "One", C: "Three" }, recommendation: "A strong choice is C" }] });
    expect(b.questions[0]!.recommended).toBeUndefined();
  });
});
