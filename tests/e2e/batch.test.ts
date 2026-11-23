import { afterEach, describe, expect, it } from "vitest";
import { cleanup, startHarness, waitFor, type Harness } from "../helpers.ts";

// Agents write question batches themselves, and models differ in the details. Whatever shape a batch comes in,
// the owner sees its options, and the answer the agent gets back names the option chosen.

let h: Harness | undefined;
afterEach(async () => {
  await cleanup(h);
  h = undefined;
});

describe("question batches in another shape", () => {
  it("are stored in the standard shape, and the answer names the chosen option", async () => {
    const odd = {
      questions: [{ id: "direction", question: "Which visual direction?", options: { A: "A — Ledger: calm", B: "B — Bloom: soft" }, recommendation: "B — Bloom. Feels welcoming." }],
    };
    h = await startHarness({
      "pm:discover": {
        steps: [
          { write: ".asf/docs/discovery/questions.json", content: JSON.stringify(odd) },
          { asf: ["ask", "@human", "--batch", ".asf/docs/discovery/questions.json"] },
        ],
      },
    });
    await h.api("POST", "/idea", { text: "A salon website", stakes: "hobby", links: [], track: "full" });
    const q = await waitFor(() => h!.project.svc.questions("open").find((x) => x.kind === "batch"), "the batch");
    const open = await h.api("GET", "/questions?status=open");
    expect(open[0].batch.questions[0]).toEqual({
      id: "direction",
      question: "Which visual direction?",
      options: [
        { key: "A", label: "Ledger: calm" },
        { key: "B", label: "Bloom: soft" },
      ],
      recommended: "B",
      why_it_matters: "Feels welcoming.",
    });
    await h.api("POST", `/questions/${q.id}/answer`, { answer: { answers: { direction: "A" } } });
    expect(String(h.project.svc.question(q.id)!.answer)).toContain("direction (Which visual direction?): A: Ledger: calm");
  });

  it("an older batch stored in its own shape is still read in the standard shape", async () => {
    h = await startHarness({});
    h.project.db.run(
      "INSERT INTO questions (id, message_id, from_agent, to_addr, kind, body, batch) VALUES ('Q-9001', NULL, 'designer-1', '@human', 'batch', '1 questions', ?)",
      JSON.stringify({ questions: [{ id: "d", question: "Pick one", options: { A: "First", B: "Second" }, recommendation: "A" }] }),
    );
    const open = await h.api("GET", "/questions?status=open");
    expect(open.find((x: { id: string }) => x.id === "Q-9001").batch.questions[0].options).toEqual([
      { key: "A", label: "First" },
      { key: "B", label: "Second" },
    ]);
  });
});
