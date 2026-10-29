import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const manifestPath = process.env.GROUNDTRUTH_SEED_MANIFEST;
test.skip(!manifestPath, "Requires a real disposable API; successful responses must not be mocked.");

test("connected owner-relative evidence and factual negatives remain inspectable", async ({ page, request }, info) => {
  const seed = JSON.parse(readFileSync(manifestPath!, "utf8"));
  const key = seed.principals["admin-a"].api_key;
  const headers = { "X-API-Key": key };
  const project = `MeridianV${info.project.use.viewport?.width}`;
  const texts = [
    `The standard ${project} review owner is the record steward.`,
    `For standard ${project} review, the record steward's deputy is the shift clerk.`,
    `${project} is a symbolic puzzle only: its transform of ABC is BCA, and it does not describe a biological sample.`,
  ];
  const ids: string[] = [];
  for (let index = 0; index < texts.length; index += 1) {
    const text = texts[index];
    const uploaded = await request.post(`${seed.api_url}/api/documents/upload`, {
      headers,
      multipart: { files: { name: `${project}-${index}.txt`, mimeType: "text/plain", buffer: Buffer.from(text) } },
    });
    expect(uploaded.ok(), await uploaded.text()).toBe(true);
    const body = await uploaded.json();
    expect(body.ingestions[0].status).toBe("completed");
    ids.push(body.documents[0].id);
  }

  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
  page.on("request", (req) => {
    const url = new URL(req.url());
    if (!["127.0.0.1", "localhost"].includes(url.hostname)) errors.push(`External request: ${url.origin}${url.pathname}`);
  });
  await page.addInitScript(() => {
    if (!sessionStorage.getItem("groundtruth.requirement.initialized")) {
      localStorage.setItem("groundtruth.source.v1", "sample");
      sessionStorage.clear();
      sessionStorage.setItem("groundtruth.requirement.initialized", "1");
    }
  });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/chat");
  await page.getByRole("button", { name: "Connection", exact: true }).click();
  await page.getByLabel("API key", { exact: true }).fill(key);
  await page.getByRole("button", { name: "Connect application" }).click();
  await expect(page.getByText("Connected local application", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "New conversation" }).click();
  await page.getByLabel("What do you need to know?").fill(`Who owns standard ${project} review, and who is the deputy?`);
  await page.getByRole("button", { name: "Ask question", exact: true }).click();
  const answer = page.getByLabel("Answer and evidence");
  await expect(answer).toContainText("This paired request uses the verified owner", { timeout: 90000 });
  await expect(answer).toContainText("record steward");
  await expect(answer).toContainText("shift clerk");
  await expect(answer.getByRole("region", { name: "Request coverage" })).toContainText("2 of 2 requirements supported");
  const ownerURL = page.url();
  expect(ownerURL).not.toContain(key);
  const ownerID = new URL(ownerURL).searchParams.get("query");
  expect(ownerID).toBeTruthy();
  const saved = await request.get(`${seed.api_url}/api/queries/${ownerID}`, { headers });
  expect(saved.ok()).toBe(true);
  const ownerRecord = await saved.json();
  expect(ownerRecord.refused).toBe(false);
  expect(ownerRecord.outcome).toBe("completed");
  expect(ownerRecord.sources.map((item: { document_id: string }) => item.document_id).sort()).toEqual(ids.slice(0, 2).sort());
  expect(ownerRecord.provenance.answer_selection.requirements[1].interpretation.kind).toBe("owner_relative_deputy");

  if (process.env.GROUNDTRUTH_SCREENSHOTS) {
    await mkdir(process.env.GROUNDTRUTH_SCREENSHOTS, { recursive: true });
    await page.screenshot({ path: path.join(process.env.GROUNDTRUTH_SCREENSHOTS, `connected-owner-relative-${info.project.use.viewport?.width}.png`), fullPage: true });
  }
  const citation = answer.locator(".gt-source-card").first();
  await citation.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog")).toContainText(project);
  await page.keyboard.press("Escape");
  await expect(citation).toBeFocused();
  await page.reload();
  await expect(answer).toContainText("This paired request uses the verified owner", { timeout: 30000 });

  await page.getByRole("button", { name: "New conversation" }).click();
  await page.getByLabel("What do you need to know?").fill(`Does ${project} symbolic puzzle describe a biological sample?`);
  await page.getByRole("button", { name: "Ask question", exact: true }).click();
  await expect(answer).toContainText("does not describe a biological sample", { timeout: 90000 });
  await expect(answer.getByRole("region", { name: "Request coverage" })).toContainText("1 of 1 requirements supported");
  const factualID = new URL(page.url()).searchParams.get("query");
  const factual = await request.get(`${seed.api_url}/api/queries/${factualID}`, { headers });
  expect(factual.ok()).toBe(true);
  const factualRecord = await factual.json();
  expect(factualRecord.refused).toBe(false);
  expect(factualRecord.sources.map((item: { document_id: string }) => item.document_id)).toEqual([ids[2]]);
  await expect(page.locator(".gt-refusal")).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});
