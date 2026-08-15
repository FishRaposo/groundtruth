import { expect, test } from "@playwright/test";

test("document version inspection and admin evidence fit a mobile viewport", async ({ page }) => {
  await page.route("**/api/documents?**", (route) => route.fulfill({
    json: {
      documents: [{
        id: "doc-1",
        title: "Policy",
        source_type: "pdf",
        source_url: null,
        status: "ready",
        metadata: null,
        created_at: "2026-08-15T12:00:00Z",
        updated_at: "2026-08-15T12:00:00Z",
      }],
      total: 1,
      limit: 50,
      offset: 0,
    },
  }));
  await page.route("**/api/v1/workflows/definitions", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/documents/doc-1/versions", (route) => route.fulfill({
    json: [{
      id: "version-1",
      document_id: "doc-1",
      version_number: 1,
      content_hash: "hash-1",
      created_at: "2026-08-15T12:00:00Z",
      change_summary: "Initial upload",
      chunk_count: 4,
    }],
  }));

  await page.goto("/documents");
  await page.getByRole("button", { name: "Versions" }).click();
  await expect(page.getByRole("region", { name: "Version history for Policy" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);

  await page.route("**/api/v1/admin/usage", (route) => route.fulfill({
    json: {
      total_requests: 3,
      total_tokens: 750,
      input_tokens: 500,
      output_tokens: 250,
      estimated_cost: 0.05,
      average_latency_ms: 120,
      p50_latency_ms: 100,
      p95_latency_ms: 180,
      p99_latency_ms: 220,
      error_rate: 0,
      cost_by_model: { offline: 0.05 },
      cost_by_prompt_version: { unversioned: 0.05 },
    },
  }));
  await page.route("**/api/v1/admin/audit", (route) => route.fulfill({ json: [] }));
  await page.goto("/admin");
  await expect(page.getByRole("heading", { name: "Admin evidence" })).toBeVisible();
  await expect(page.getByText("750")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
});
