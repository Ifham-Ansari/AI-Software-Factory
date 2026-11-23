import { expect, test } from "@playwright/test";
import { startFakeLlm, type FakeLlm } from "../../fake-claude/src/llm.ts";
import { cleanup, DEFAULT_BUILD_SCENARIO, goto, openDashboard, startHarness, type Harness } from "./harness.ts";

// The built-in engine's screens: the team's API keys, and choosing the engine and models in Settings.

let h: Harness | undefined;
let llm: FakeLlm | undefined;
test.afterEach(async () => {
  await llm?.close();
  llm = undefined;
  await cleanup(h);
  h = undefined;
});

test("API keys: teammates add their keys (shown masked), test them, and remove one", async ({ page }) => {
  h = await startHarness(DEFAULT_BUILD_SCENARIO);
  llm = await startFakeLlm({ scenarioFile: process.env.ASF_FAKE_SCENARIO!, stateDir: h.stateDir });
  await openDashboard(page, h, "keys");
  await expect(page.getByTestId("engine-status")).toContainText("Claude Code");

  const form = page.getByTestId("add-key");
  const add = async (label: string, key: string) => {
    await form.getByLabel("Provider").selectOption("custom");
    await form.getByLabel("Whose key").fill(label);
    await form.getByLabel("API key").fill(key);
    await form.getByLabel("Base URL").fill(llm!.url);
    await form.getByRole("button", { name: "Add key" }).click();
  };
  await add("Ayesha", "sk-e2e-secret-123456");
  // Testing the key also picks its best model, shown in the toast and on the key.
  await expect(page.getByText("Ayesha's key works (4 models). Best model: fake-model, used automatically.")).toBeVisible();
  const list = page.getByTestId("keys-list");
  await expect(list).toContainText("Ayesha");
  await expect(list).toContainText("••••3456");
  await expect(list.locator("li", { hasText: "Ayesha" })).toContainText("best model: fake-model");
  await expect(form.getByLabel("API key")).toHaveValue("");

  await add("Bilal", "bad-key-000000");
  await expect(page.getByText(/Bilal's key did not work/)).toBeVisible();
  const bilal = list.locator("li", { hasText: "Bilal" });
  await expect(bilal).toContainText("rejected");
  await expect(page.getByTestId("team-usage")).toContainText("Ayesha");
  // The full key is never sent back to the browser.
  expect(await page.content()).not.toContain("sk-e2e-secret");

  await bilal.getByRole("button", { name: "Remove" }).click();
  await page.getByTestId("remove-key").getByRole("button", { name: "Remove key" }).click();
  await expect(list.locator("li", { hasText: "Bilal" })).toHaveCount(0);
  expect(h.keys!.list().map((k) => k.label)).toEqual(["Ayesha"]);
});

test("Questions: a batch an agent wrote in another shape shows its options and can be answered", async ({ page }) => {
  h = await startHarness(DEFAULT_BUILD_SCENARIO);
  // As a free model wrote it: options as a map, and a recommendation sentence.
  h.project.db.run(
    "INSERT INTO questions (id, message_id, from_agent, to_addr, kind, body, batch) VALUES ('Q-9001', NULL, 'designer-1', '@human', 'batch', '1 questions', ?)",
    JSON.stringify({
      questions: [
        {
          id: "design-direction",
          question: "Choose the visual direction.",
          options: { A: "A — Ledger: calm and precise.", B: "B — Atelier: dark and moody.", C: "C — Bloom: soft and modern." },
          recommendation: "C — Bloom. The dual accents separate hair from nails.",
        },
      ],
    }),
  );
  await openDashboard(page, h, "questions");
  await expect(page.getByTestId("screen-error")).toHaveCount(0);
  await expect(page.getByTestId("batch-q-design-direction")).toContainText("Choose the visual direction.");
  await expect(page.getByText("Bloom: soft and modern.")).toBeVisible();
  await expect(page.getByText("The dual accents separate hair from nails.")).toBeVisible();
  // Nothing looks chosen until the owner picks; then the pick is unmistakable.
  const card = page.getByTestId("batch-q-design-direction");
  await expect(card.getByText("your choice")).toHaveCount(0);
  await page.getByText("Ledger: calm and precise.").click();
  await expect(card.locator("label[data-selected]")).toHaveCount(1);
  await expect(card.locator("label[data-selected]")).toContainText("Ledger: calm and precise.");
  await expect(card.locator("label[data-selected]")).toContainText("your choice");
  await page.getByText("Atelier: dark and moody.").click();
  await expect(card.locator("label[data-selected]")).toContainText("Atelier: dark and moody.");
  await page.getByText("Ledger: calm and precise.").click();
  await page.getByRole("button", { name: "Submit answers" }).click();
  await expect.poll(() => h!.project.svc.question("Q-9001")?.status).toBe("answered");
  expect(String(h.project.svc.question("Q-9001")!.answer)).toContain("A: Ledger: calm and precise.");
});

test("Usage-limit wait: the header and Needs you say until when, and Try now retries", async ({ page }) => {
  h = await startHarness(DEFAULT_BUILD_SCENARIO);
  h.project.svc.patchState({ limitedUntil: Date.now() + 3_600_000 });
  await openDashboard(page, h, "needs");
  const pill = page.getByTestId("limit-wait");
  await expect(pill).toContainText("waiting for usage limits until");
  await expect(page.getByText(/Agents are waiting for usage limits to reset/)).toBeVisible();
  await pill.getByRole("button", { name: "Try now" }).click();
  await expect(pill).toHaveCount(0);
  expect(h.project.svc.state.limitedUntil).toBeNull();
});

test("Settings: switch to the built-in engine and pick models from the providers' live lists", async ({ page }) => {
  h = await startHarness(DEFAULT_BUILD_SCENARIO);
  llm = await startFakeLlm({ scenarioFile: process.env.ASF_FAKE_SCENARIO!, stateDir: h.stateDir });
  const key = h.keys!.add({ provider: "custom", label: "Ayesha", key: "sk-e2e-123456", baseUrl: llm.url });
  await openDashboard(page, h, "settings");

  await page.getByRole("radio", { name: /Built-in engine/ }).check();
  await expect(page.getByTestId("engine-key-count")).toContainText("1 working key");
  // The key's best model is picked without any setup, and used while the lists are empty.
  await expect(page.getByTestId("engine-auto")).toBeChecked();
  await expect(page.getByTestId("engine-auto-picks")).toContainText(`${key.id}:fake-model`);
  await expect(page.getByTestId("engine-auto-picks")).toContainText("Your lists are empty, so the automatic choice is used for every run");
  // Light work goes to the small model first, complex work to the most capable.
  await expect(page.getByTestId("route-light")).toContainText(`${key.id}:fake-mini-8b`);
  await expect(page.getByTestId("route-heavy").locator("span.mono").first()).toHaveText(`${key.id}:fake-model`);
  const strong = page.getByTestId("chain-strong");
  await strong.getByLabel("Add a model").fill(`${key.id}:fake-model`);
  await strong.getByRole("button", { name: "Add", exact: true }).click();
  const fast = page.getByTestId("chain-fast");
  await fast.getByLabel("Add a model").fill(`${key.id}:fake-fast`);
  await fast.getByLabel("Add a model").press("Enter");
  // A model its provider does not offer (a paid or retired one) is flagged before it fails every run.
  await expect(page.getByTestId("model-not-free")).toHaveCount(0);
  await strong.getByLabel("Add a model").fill(`${key.id}:paid-model-405b`);
  await strong.getByLabel("Add a model").press("Enter");
  await expect(strong.getByTestId("model-not-free")).toHaveCount(1);
  await strong.getByRole("button", { name: `Remove ${key.id}:paid-model-405b` }).click();
  await expect(page.getByTestId("model-not-free")).toHaveCount(0);
  await page.getByRole("button", { name: "Save settings" }).click();
  await expect(page.getByText("Settings saved")).toBeVisible();
  expect(h.project.svc.settings).toMatchObject({ engine: "builtin", engine_models: { strong: [`${key.id}:fake-model`], fast: [`${key.id}:fake-fast`] } });

  // Without a working key, the Idea screen says so before anyone submits a request.
  h.keys!.remove(key.id);
  await goto(page, h, "idea");
  await expect(page.getByTestId("engine-readiness")).toContainText("no working API key");
  await page.getByTestId("engine-readiness").getByRole("link", { name: "Add a free API key" }).click();
  await expect(page.getByTestId("add-key")).toBeVisible();
});
