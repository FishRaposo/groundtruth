import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { mkdir } from "node:fs/promises";
import path from "node:path";
interface Seed {
  api_url: string;
  legacy_query_id: string;
  principals: Record<string, { api_key: string }>;
  reader_error_query_id?: string;
  browser: {
    question: string; expected_quote: string; document_id: string;
    reader_contract?: string; expected_answer_span?: string;
  };
}
const manifestPath = process.env.GROUNDTRUTH_SEED_MANIFEST;
test.skip(
  !manifestPath,
  "A real disposable API seed manifest is required; no successful API mocks are permitted.",
);
test("actual ingestion, query, immutable sources, decisions, identity and recovery", async ({
  page,
}, info) => {
  const seed: Seed = JSON.parse(readFileSync(manifestPath!, "utf8"));
  const errors: string[] = [];
  let deliberateOutage = false;
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (!["127.0.0.1", "localhost"].includes(url.hostname))
      errors.push(`Unexpected external request: ${url.origin}${url.pathname}`);
  });
  page.on("console", (message) => {
    if (
      message.type() === "error" &&
      !deliberateOutage &&
      !/403|401/.test(message.text())
    )
      errors.push(message.text());
  });
  await page.addInitScript(() => {
    if (!sessionStorage.getItem("groundtruth.live.initialized")) {
      localStorage.setItem("groundtruth.source.v1", "sample");
      sessionStorage.clear();
      sessionStorage.setItem("groundtruth.live.initialized", "1");
    }
  });
  await page.emulateMedia({ reducedMotion: "reduce" });
  const connect = async (key: string) => {
    await page.getByRole("button", { name: "Connection", exact: true }).click();
    await page.getByLabel("API key", { exact: true }).fill(key);
    await page.getByRole("button", { name: "Connect application" }).click();
    await expect(
      page.getByText("Connected local application", { exact: true }),
    ).toBeVisible();
  };
  const fits = async () =>
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  const shot = async (label: string) => {
    if (process.env.GROUNDTRUTH_SCREENSHOTS) {
      await mkdir(process.env.GROUNDTRUTH_SCREENSHOTS, { recursive: true });
      await page.evaluate(() => {
        if (document.activeElement?.classList.contains("gt-skip"))
          (document.activeElement as HTMLElement).blur();
        window.scrollTo(0, 0);
      });
      await page.screenshot({
        path: path.join(
          process.env.GROUNDTRUTH_SCREENSHOTS,
          `${label}-${info.project.use.viewport?.width}.png`,
        ),
        fullPage:
          !(await page.getByRole("dialog").isVisible()) &&
          !/(documents|admin)$/.test(label),
      });
    }
  };
  await page.goto("/chat");
  await connect(seed.principals["admin-a"].api_key);
  await expect(page.getByText(/admin-a.*ops-a/)).toBeVisible();
  await page.goto(`/chat?query=${seed.legacy_query_id}`);
  await expect(page.getByLabel("Answer and evidence")).toContainText("Legacy outcome unknown");
  await expect(page.getByLabel("Answer and evidence").locator(".gt-source-card")).toHaveCount(0);
  await page.getByText("Retrieval trace & provenance", { exact: true }).click();
  await expect(page.getByLabel("Answer and evidence")).toContainText('"provenance": "unknown"');
  await page.reload();
  await expect(page.getByLabel("Answer and evidence")).toContainText("Legacy outcome unknown");
  await shot("connected-legacy");
  if (seed.reader_error_query_id) {
    await page.goto(`/chat?query=${seed.reader_error_query_id}`);
    await expect(page.getByLabel("Answer and evidence")).toContainText("Reader failed");
    await expect(page.locator(".gt-refusal")).toHaveCount(0);
    await shot("connected-reader-error");
  }
  await page.getByRole("button", { name: "New conversation" }).click();
  await expect(
    page.getByRole("combobox", { name: "Conversation", exact: true }),
  ).not.toHaveValue("");
  await page
    .getByLabel("What do you need to know?")
    .fill(seed.browser.question);
  await page.getByRole("button", { name: "Ask question", exact: true }).click();
  const answer = page.getByLabel("Answer and evidence");
  const expectedAnswer = seed.browser.expected_answer_span || (seed.browser.reader_contract ? undefined : seed.browser.expected_quote);
  if (expectedAnswer) await expect(answer).toContainText(expectedAnswer, { timeout: 60000 });
  if (seed.browser.reader_contract) {
    await expect(answer.getByLabel("Answer selection evidence")).toContainText("Local extractive reader", { timeout: 60000 });
    await expect(answer.getByLabel("Answer selection evidence")).toContainText(seed.browser.reader_contract);
  }
  const savedURL = page.url();
  expect(savedURL).toContain("query=");
  expect(savedURL).not.toContain(seed.principals["admin-a"].api_key);
  const citation = answer.locator(".gt-source-card").first();
  await citation.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog")).toContainText(
    seed.browser.expected_quote,
  );
  if (seed.browser.reader_contract) {
    const marks = page.getByRole("dialog").locator("mark[data-answer-span=true]");
    await expect(marks.first()).toBeVisible();
    if (seed.browser.expected_answer_span) await expect(marks.first()).toContainText(seed.browser.expected_answer_span);
    await expect(page.getByLabel("Canonical quoted evidence")).toContainText(seed.browser.expected_quote);
  }
  await page.getByRole("dialog").getByText("Immutable source identity").click();
  await expect(page.getByRole("dialog")).toContainText("Content SHA-256");
  await shot("connected-source");
  await page.keyboard.press("Escape");
  await expect(citation).toBeFocused();
  await page.reload();
  if (expectedAnswer) await expect(answer).toContainText(expectedAnswer, { timeout: 60000 });
  if (seed.browser.reader_contract) await expect(answer.getByLabel("Answer selection evidence")).toContainText(seed.browser.reader_contract);
  await page.getByLabel("Stream the actual answer (SSE)").check();
  await page
    .getByLabel("What do you need to know?")
    .fill(seed.browser.question);
  await page.getByRole("button", { name: "Ask question", exact: true }).click();
  await expect(page).not.toHaveURL(savedURL, { timeout: 60000 });
  await expect(page.getByLabel("What do you need to know?")).toHaveValue("");
  if (expectedAnswer) await expect(answer).toContainText(expectedAnswer);
  if (seed.browser.reader_contract) await expect(answer.getByLabel("Answer selection evidence")).toContainText(seed.browser.reader_contract);
  await shot("connected-answer");
  const supportedURL = page.url();
  await page
    .getByLabel("What do you need to know?")
    .fill("What is the CEO salary?");
  await page.getByRole("button", { name: "Ask question", exact: true }).click();
  await expect(page).not.toHaveURL(supportedURL, { timeout: 60000 });
  await expect(answer.locator(".gt-badge").first()).toContainText("refused");
  await expect(answer.locator(".gt-refusal")).toBeVisible();
  await expect(answer.locator(".gt-source-card")).toHaveCount(0);
  const previousConversation = await page
    .getByRole("combobox", { name: "Conversation", exact: true })
    .inputValue();
  await page.getByRole("button", { name: "New conversation" }).click();
  await expect(
    page.getByRole("combobox", { name: "Conversation", exact: true }),
  ).not.toHaveValue(previousConversation);
  await expect(page).not.toHaveURL(/query=/);
  await expect(page.getByLabel("Answer and evidence")).not.toBeVisible();
  await page.getByRole("link", { name: "Documents", exact: true }).click();
  const filename = `browser-proof-${info.project.name}-${Date.now()}.txt`;
  const file = (version: number) => ({
    name: filename,
    mimeType: "text/plain",
    buffer: Buffer.from(
      `Browser acceptance rollback runbook version ${version}. Pause the deployment queue. Restore the staging snapshot and verify all health checks. This controlled fixture is owned by the local browser test. ${version === 2 ? "A reviewer must approve reopening traffic." : "Record the rollback in the incident log."}`,
    ),
  });
  await page.getByLabel("Choose documents").setInputFiles(file(1));
  await page.getByRole("button", { name: "Upload & ingest" }).click();
  const docCard = page.getByRole("article").filter({
    has: page.getByRole("heading", { name: filename, exact: true }),
  });
  await expect(docCard).toContainText("ready", { timeout: 60000 });
  if (seed.browser.reader_contract) {
    await page.getByRole("link", { name: "Chat", exact: true }).click();
    await page.getByRole("combobox", { name: "Document scope", exact: true }).selectOption({ label: filename });
    await page.getByLabel("What do you need to know?").fill("What must be paused before restoring the staging snapshot?");
    await page.getByRole("button", { name: "Ask question", exact: true }).click();
    await expect(answer.locator(".gt-answer-text")).toContainText("deployment queue", { timeout: 60000 });
    await expect(answer.getByLabel("Answer selection evidence")).toContainText(seed.browser.reader_contract);
    const uploadedURL = page.url();
    await answer.locator(".gt-source-card").first().click();
    await expect(page.getByLabel("Canonical quoted evidence")).toContainText("Record the rollback in the incident log.");
    await expect(page.getByRole("dialog").locator("mark[data-answer-span=true]").first()).toContainText("deployment queue");
    await shot("connected-upload-reader");
    await page.keyboard.press("Escape");
    await page.reload();
    await expect(answer.locator(".gt-answer-text")).toContainText("deployment queue", { timeout: 60000 });
    expect(page.url()).toBe(uploadedURL);
    await page.getByRole("link", { name: "Documents", exact: true }).click();
  }
  await docCard.getByRole("button", { name: "Versions & evidence" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Version 1");
  await dialog.getByLabel("Replacement file").setInputFiles(file(2));
  await dialog.getByRole("button", { name: "Submit new version" }).click();
  await expect(dialog).not.toBeVisible({ timeout: 60000 });
  await expect(docCard).toContainText("Version 2");
  await docCard.getByRole("button", { name: "Versions & evidence" }).click();
  await dialog
    .getByRole("button", { name: "Compare previous and current" })
    .click();
  await expect(dialog.getByLabel("Version comparison")).toContainText(
    "reviewer",
  );
  await dialog.getByRole("button", { name: "Inspect passage v1" }).click();
  await expect(dialog.getByLabel("Version snapshot")).toContainText(
    "incident log",
  );
  await dialog.getByRole("button", { name: "Restore v1", exact: true }).click();
  await dialog.getByRole("button", { name: "Confirm restore" }).click();
  await expect(dialog).not.toBeVisible({ timeout: 60000 });
  await expect(docCard).toContainText("Version 3");
  await shot("connected-documents");
  await page.getByRole("link", { name: "Workflows", exact: true }).click();
  await page
    .getByRole("combobox", { name: "Document", exact: true })
    .selectOption(seed.browser.document_id);
  await page
    .getByRole("combobox", { name: "Workflow definition", exact: true })
    .selectOption({ index: 1 });
  for (const [action, expected] of [
    ["Approve", "completed"],
    ["Reject", "rejected"],
    ["Cancel workflow", "cancelled"],
  ] as const) {
    await page.getByRole("button", { name: "Start review" }).click();
    await expect(
      page.getByLabel("Selected workflow").locator(".gt-badge"),
    ).toHaveText(/pending|in_progress/);
    await page.getByRole("button", { name: action, exact: true }).click();
    await expect(page.getByLabel("Selected workflow")).toContainText(expected);
  }
  await page.getByRole("link", { name: "Admin", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Audit history" }),
  ).toBeVisible();
  await expect(
    page.getByText("Recorded requests", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Usage measurements and provenance", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Unknown", { exact: true })).toBeVisible();
  await expect
    .poll(() =>
      page.getByLabel("Recorded audit events").locator("article").count(),
    )
    .toBeGreaterThan(0);
  await shot("connected-admin");
  await connect(seed.principals["viewer-a"].api_key);
  await expect(
    page.getByText(/Administrator access is required/),
  ).toBeVisible();
  await page.getByRole("link", { name: "Chat", exact: true }).click();
  await expect(page.getByLabel("Answer and evidence")).not.toBeVisible();
  await expect(
    page.getByRole("combobox", { name: "Conversation", exact: true }),
  ).toHaveValue("");
  await connect(seed.principals["admin-a"].api_key);
  deliberateOutage = true;
  await page.route(`${seed.api_url}/**`, (route) => route.abort("failed"));
  await page.goto("/documents");
  await expect(
    page
      .getByRole("alert")
      .filter({ hasText: "Connection or operation failed" }),
  ).toContainText("not been replaced with sample data");
  await expect(
    page.getByText("Interactive sample data", { exact: true }),
  ).not.toBeVisible();
  await page.unroute(`${seed.api_url}/**`);
  await page.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: filename, exact: true }),
  ).toBeVisible();
  deliberateOutage = false;
  for (const route of [
    "/",
    "/chat",
    "/documents",
    "/workflows",
    "/admin",
    "/workflow",
  ]) {
    await page.goto(route);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await fits();
    await expect(page.locator("nextjs-portal")).toHaveCount(0);
  }
  expect(errors).toEqual([]);
});
