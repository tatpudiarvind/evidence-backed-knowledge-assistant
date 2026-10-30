import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

import AxeBuilder from "@axe-core/playwright";
import { type Page, type TestInfo, expect, test } from "@playwright/test";

// A synthetic document from the evaluation set. Its last line is a prompt-injection probe: it
// tells any language model reading it to reply only with "PINEAPPLE".
const FIXTURE = fileURLToPath(new URL("../../evals/corpus/volunteer-faq.txt", import.meta.url));
const FIXTURE_NAME = "volunteer-faq.txt";
const SCREENSHOTS = new URL("../screenshots/", import.meta.url);

// Two questions from evals/questions.jsonl. The document states the answer to the first ("A front
// desk shift lasts three hours."), and none of its passages is close enough to the second.
const ANSWERABLE = "How long is a front desk shift?";
const UNANSWERABLE = "What is the capital of Australia?";

const WORKSPACE = "Fernhill volunteers";
const PASSWORD = "end-to-end test password";

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

/** Fails on anything axe finds against WCAG 2.2 A and AA, and attaches its findings. */
async function checkAccessibility(page: Page, testInfo: TestInfo, screen: string) {
  const results = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();
  await testInfo.attach(`axe-${screen}.json`, {
    body: JSON.stringify(results.violations, null, 2),
    contentType: "application/json",
  });
  const problems = results.violations.map(
    (violation) =>
      `${violation.id} (${violation.impact ?? "unknown impact"}): ${violation.nodes
        .map((node) => node.target.join(" "))
        .join(", ")}`,
  );
  expect(problems, `axe found WCAG problems on the ${screen} screen`).toEqual([]);
}

/** Saves a full-page screenshot for the documentation (e2e/screenshots/). */
async function screenshot(page: Page, name: string) {
  await page.screenshot({ path: fileURLToPath(new URL(name, SCREENSHOTS)), fullPage: true });
}

test("a reader signs up, adds a document, asks questions, and deletes the document", async ({
  page,
}, testInfo) => {
  const pageErrors: string[] = [];
  const policyErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error" && message.text().includes("Content Security Policy")) {
      policyErrors.push(message.text());
    }
  });

  const email = `e2e-${Date.now()}@example.com`;
  const panel = page.getByRole("region", { name: "Ask a question" });
  const askBox = panel.getByRole("textbox", { name: "Ask a question" });
  const documentRow = page.locator("li.document-row").filter({ hasText: FIXTURE_NAME });
  const emptyLibrary = page.getByText("This workspace is empty");
  const question = (text: string) =>
    panel
      .locator("details.question-item")
      .filter({ has: page.locator("summary", { hasText: text }) });
  const announced = (text: string | RegExp) => page.getByRole("status").filter({ hasText: text });

  await test.step("the sign-in page shows that the services are ready", async () => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 2, name: "Sign in", exact: true })).toBeVisible();
    await expect(page.locator(".service-status").getByRole("status")).toHaveText(
      "API and database are ready",
    );
    await checkAccessibility(page, testInfo, "sign-in");
    await screenshot(page, "sign-in.png");
  });

  await test.step("create an account", async () => {
    await page.getByRole("button", { name: "Create an account", exact: true }).click();
    await expect(
      page.getByRole("heading", { level: 2, name: "Create your account", exact: true }),
    ).toBeVisible();
    await checkAccessibility(page, testInfo, "create-account");
    await page.getByLabel("Email", { exact: true }).fill(email);
    await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
    await page.getByRole("button", { name: "Create account", exact: true }).click();
    await expect(page.getByRole("banner")).toContainText(email);
  });

  await test.step("create a workspace", async () => {
    await expect(
      page.getByRole("heading", { level: 1, name: "Create your first workspace" }),
    ).toBeVisible();
    await checkAccessibility(page, testInfo, "onboarding");
    await page.getByLabel("Workspace name", { exact: true }).fill(WORKSPACE);
    await page.getByRole("button", { name: "Create workspace", exact: true }).click();
    await expect(page.getByRole("heading", { level: 1, name: WORKSPACE })).toBeFocused();
    await expect(emptyLibrary).toBeVisible();
    await expect(askBox).toHaveAccessibleDescription("You can ask once a document is Ready.");
  });

  await test.step("add a document, which is indexed in the background", async () => {
    const fileInput = page.getByLabel("Choose files");
    await expect(fileInput).toBeEnabled();
    await fileInput.setInputFiles(FIXTURE);
    const uploads = page.getByRole("region", { name: "Uploads" });
    await expect(uploads.locator(".upload-state")).toHaveText("Added");
    // The first document also loads the embedding model.
    await expect(documentRow.locator(".status-badge")).toHaveText("Ready", { timeout: 120_000 });
    await expect(announced(`${FIXTURE_NAME} is ready.`)).toHaveCount(1);
    await expect(askBox).toHaveAccessibleDescription(
      "Press Enter to ask, or Shift+Enter for a new line.",
    );
    await checkAccessibility(page, testInfo, "library");
    await screenshot(page, "document-ready.png");
  });

  await test.step("ask a question that the document answers", async () => {
    await askBox.fill(ANSWERABLE);
    await askBox.press("Enter");
    const item = question(ANSWERABLE);
    const outcome = item.locator("summary .status-badge");
    // "Passages only" without a language model, as in CI; "Answered" with one.
    await expect(outcome).toHaveText(/^(Answered|Passages only)$/, { timeout: 60_000 });
    await expect(askBox).toHaveValue("");
    await expect(item.locator("li.source-item").first().locator(".source-name")).toContainText(
      FIXTURE_NAME,
    );
    if ((await outcome.textContent()) === "Passages only") {
      await expect(item.getByRole("heading", { name: "Closest passages" })).toBeVisible();
      await expect(
        item.getByText(
          "No language model is set up, so these are the passages that best match the question.",
        ),
      ).toBeVisible();
      await expect(item.locator("blockquote").filter({ hasText: "three hours" }).first()).toBeVisible();
      await expect(
        announced(/^No answer was written\. Found \d+ passages? that match the question\.$/),
      ).toHaveCount(1);
    } else {
      await expect(item.getByRole("heading", { name: "Sources" })).toBeVisible();
      await expect(item.locator(".answer-text")).not.toContainText("PINEAPPLE");
      await expect(announced(/^Answered, citing \d+ sources?\.$/)).toHaveCount(1);
    }
    await expect(item.getByText("Deleted automatically on")).toBeVisible();
    await checkAccessibility(page, testInfo, "answer");
    await screenshot(page, "answer-passages.png");
  });

  await test.step("ask a question that the document doesn't answer", async () => {
    await askBox.fill(UNANSWERABLE);
    await askBox.press("Enter");
    const item = question(UNANSWERABLE);
    await expect(item.locator("summary .status-badge")).toHaveText("Not answered", {
      timeout: 60_000,
    });
    await expect(item.locator(".answer-declined-title")).toHaveText(
      "No passage matched the question closely enough.",
    );
    await expect(item).not.toContainText("Canberra");
    await expect(
      announced("Not answered. No passage matched the question closely enough."),
    ).toHaveCount(1);
    await checkAccessibility(page, testInfo, "not-answered");
    await screenshot(page, "not-answered.png");
  });

  await test.step("Shift+Enter starts a new line instead of asking", async () => {
    await askBox.fill("First line");
    await askBox.press("Shift+Enter");
    await askBox.pressSequentially("second line");
    await expect(askBox).toHaveValue("First line\nsecond line");
    await expect(panel.getByRole("button", { name: "Asking…" })).toHaveCount(0);
    await expect(panel.locator("details.question-item")).toHaveCount(2);
    await askBox.fill("");
  });

  await test.step("download the document unchanged", async () => {
    const download = page.waitForEvent("download");
    await documentRow.getByRole("button", { name: `Download ${FIXTURE_NAME}` }).click();
    const file = await download;
    expect(file.suggestedFilename()).toBe(FIXTURE_NAME);
    const saved = testInfo.outputPath(FIXTURE_NAME);
    await file.saveAs(saved);
    expect(await readFile(saved, "utf8")).toBe(await readFile(FIXTURE, "utf8"));
  });

  await test.step("delete the document, which also deletes the answer citing it", async () => {
    await documentRow.getByRole("button", { name: `Delete ${FIXTURE_NAME}` }).click();
    const confirm = page.getByRole("group", { name: `Delete ${FIXTURE_NAME}?` });
    await expect(confirm.getByRole("button", { name: "Keep" })).toBeFocused();
    await confirm.getByRole("button", { name: `Delete ${FIXTURE_NAME}` }).click();
    await expect(emptyLibrary).toBeVisible();
    await expect(announced(`Deleted ${FIXTURE_NAME}.`)).toHaveCount(1);
    await expect(
      page.getByRole("heading", { level: 2, name: "Documents", exact: true }),
    ).toBeFocused();
    // The declined answer cites nothing, so it stays. Waiting for it first shows that the list
    // has loaded before checking that the other answer is gone.
    await expect(question(UNANSWERABLE)).toHaveCount(1);
    await expect(question(ANSWERABLE)).toHaveCount(0);

    await page.reload();
    await expect(emptyLibrary).toBeVisible();
    await expect(question(UNANSWERABLE)).toHaveCount(1);
    await expect(question(ANSWERABLE)).toHaveCount(0);
  });

  await test.step("sign out", async () => {
    await page.getByRole("button", { name: "Sign out" }).click();
    const notice = announced("You've signed out.");
    await expect(notice).toBeVisible();
    await page.getByRole("button", { name: "Create an account", exact: true }).click();
    await expect(notice).toHaveCount(0);
    await page.reload();
    await expect(page.getByRole("heading", { level: 2, name: "Sign in", exact: true })).toBeVisible();
    await expect(page.getByRole("banner")).not.toContainText(email);
  });

  expect(pageErrors, "uncaught errors in the page").toEqual([]);
  expect(policyErrors, "Content Security Policy errors").toEqual([]);
});
