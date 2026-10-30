import { expect, test, type Locator } from "@playwright/test";
import { readFileSync } from "node:fs";
import { mkdir } from "node:fs/promises";
import path from "node:path";

interface Seed {
  api_url: string;
  reader_error_query_id: string;
  principals: Record<string, { api_key: string }>;
  browser?: { reader_contract?: string };
}
const manifestPath = process.env.GROUNDTRUTH_SEED_MANIFEST;
test.skip(!manifestPath, "Actual disposable API seed required; successful API mocks are prohibited.");

test("diagnostic only: fresh factual reader, immutable spans, refusal, error and recovery", async ({ page }, info) => {
  const seed: Seed = JSON.parse(readFileSync(manifestPath!, "utf8"));
  const readerContract = seed.browser?.reader_contract ?? "requirement-evidence-v2";
  const errors: string[] = [];
  let deliberateOutage = false;
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error" && !deliberateOutage) errors.push(message.text());
  });
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (!["127.0.0.1", "localhost"].includes(url.hostname)) errors.push(`Unexpected external request: ${url.origin}${url.pathname}`);
  });
  await page.addInitScript(() => {
    if (!sessionStorage.getItem("groundtruth.diagnostic.initialized")) {
      localStorage.setItem("groundtruth.source.v1", "sample");
      sessionStorage.clear();
      sessionStorage.setItem("groundtruth.diagnostic.initialized", "1");
    }
  });
  await page.emulateMedia({ reducedMotion: "reduce" });
  const shot = async (label: string, region?: Locator) => {
    const directory = process.env.GROUNDTRUTH_SCREENSHOTS;
    if (!directory) return;
    await mkdir(directory, { recursive: true });
    const options = { path: path.join(directory, `diagnostic-${label}-${info.project.use.viewport?.width}.png`) };
    if (region) await region.screenshot(options);
    else await page.screenshot({ ...options, fullPage: false });
  };
  const fits = async () => expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.goto("/chat");
  await expect(page).toHaveTitle(/GroundTruth/);
  await page.getByRole("button", { name: "Connection", exact: true }).click();
  await page.getByLabel("API key", { exact: true }).fill(seed.principals["admin-a"].api_key);
  await page.getByRole("button", { name: "Connect application" }).click();
  await expect(page.getByText("Connected local application", { exact: true })).toBeVisible();
  await expect(page.getByText(/admin-a.*ops-a/)).toBeVisible();

  const filename = `coverage-diagnostic-${info.project.name}-${Date.now()}.txt`;
  const content = "🧭 Bridge repair approval.\nAnika authorizes bridge repairs. The inspection window lasts 14 minutes. Operators log approval before work starts.\nThis synthetic runbook belongs to the local browser diagnostic.";
  await page.getByRole("link", { name: "Documents", exact: true }).click();
  await page.getByLabel("Choose documents").setInputFiles({ name: filename, mimeType: "text/plain", buffer: Buffer.from(content) });
  await page.getByRole("button", { name: "Upload & ingest" }).click();
  const doc = page.getByRole("article").filter({ has: page.getByRole("heading", { name: filename, exact: true }) });
  await expect(doc).toContainText("ready", { timeout: 60000 });
  await page.getByRole("link", { name: "Chat", exact: true }).click();
  await page.getByRole("button", { name: "New conversation" }).click();
  await expect(page.getByRole("combobox", { name: "Conversation", exact: true })).not.toHaveValue("");
  const selectDocument = async () => page.getByRole("combobox", { name: "Document scope", exact: true }).selectOption({ label: filename });
  const ask = async (question: string) => {
    await page.getByLabel("What do you need to know?").fill(question);
    await page.getByRole("button", { name: "Ask question", exact: true }).click();
  };
  await selectDocument();
  await ask("Who authorizes bridge repairs?");
  const answer = page.getByLabel("Answer and evidence");
  await expect(answer.locator(".gt-answer-text")).toContainText("Anika", { timeout: 60000 });
  await expect(answer.getByLabel("Answer selection evidence")).toContainText("Local QA-only extraction");
  await expect(answer.getByLabel("Answer selection evidence")).toContainText(readerContract);
  const savedURL = page.url();
  expect(savedURL).toContain("query=");
  expect(savedURL).not.toContain(seed.principals["admin-a"].api_key);
  await shot("answer", answer);
  await answer.locator(".gt-source-card").first().click();
  const dialog = page.getByRole("dialog");
  const canonical = page.getByLabel("Canonical quoted evidence");
  await expect(canonical).toContainText("🧭 Bridge repair approval.");
  await expect(canonical).toContainText("This synthetic runbook belongs to the local browser diagnostic.");
  await expect(dialog.locator("mark[data-answer-span=true]").first()).toContainText("Anika");
  await dialog.getByText("Immutable source identity", { exact: true }).click();
  const hash = await dialog.getByText("Content SHA-256", { exact: true }).evaluate((node) => node.nextElementSibling?.textContent);
  expect(hash).toMatch(/^[a-f0-9]{64}$/);
  await shot("source", dialog);
  await page.keyboard.press("Escape");
  await page.reload();
  await expect(answer.locator(".gt-answer-text")).toContainText("Anika", { timeout: 60000 });
  expect(page.url()).toBe(savedURL);
  await answer.locator(".gt-source-card").first().click();
  await dialog.getByText("Immutable source identity", { exact: true }).click();
  expect(await dialog.getByText("Content SHA-256", { exact: true }).evaluate((node) => node.nextElementSibling?.textContent)).toBe(hash);
  await expect(dialog.locator("mark[data-answer-span=true]").first()).toContainText("Anika");
  await page.keyboard.press("Escape");
  await selectDocument();
  await page.getByLabel("Stream the actual answer (SSE)").check();
  await ask("Who authorizes bridge repairs?");
  await expect(page).not.toHaveURL(savedURL, { timeout: 60000 });
  await expect(answer.locator(".gt-answer-text")).toContainText("Anika");
  await expect(answer.getByLabel("Answer selection evidence")).toContainText(readerContract);
  const supportedURL = page.url();
  await ask("What is the CEO salary?");
  await expect(page).not.toHaveURL(supportedURL, { timeout: 60000 });
  await expect(answer.locator(".gt-refusal")).toBeVisible();
  await expect(answer.locator(".gt-source-card")).toHaveCount(0);
  await shot("refusal", answer);
  expect(seed.reader_error_query_id).toBeTruthy();
  await page.goto(`/chat?query=${encodeURIComponent(seed.reader_error_query_id)}`);
  await expect(answer).toContainText("Reader failed");
  await expect(answer).toContainText("This is an execution failure");
  await expect(answer.locator(".gt-refusal")).toHaveCount(0);
  await expect(answer.locator(".gt-source-card")).toHaveCount(0);
  await shot("reader-error", answer);

  deliberateOutage = true;
  await page.route(`${seed.api_url}/**`, (route) => route.abort("failed"));
  await page.goto("/documents");
  await expect(page.getByRole("alert").filter({ hasText: "Connection or operation failed" })).toContainText("not been replaced with sample data");
  await expect(page.getByText("Interactive sample data", { exact: true })).not.toBeVisible();
  await shot("outage");
  await page.unroute(`${seed.api_url}/**`);
  await page.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(page.getByRole("heading", { name: filename, exact: true })).toBeVisible();
  deliberateOutage = false;
  for (const route of ["/", "/chat", "/documents", "/workflows", "/admin", "/workflow"]) {
    await page.goto(route);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await fits();
    await expect(page.locator("nextjs-portal")).toHaveCount(0);
  }
  expect(errors).toEqual([]);
});
