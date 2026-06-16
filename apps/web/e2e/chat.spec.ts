import { test, expect } from "@playwright/test";

/**
 * Chat smoke test.
 *
 * Runs against the dev server with no backend API available, so the chat
 * interface should degrade to demo mode and still produce a grounded answer
 * with highlighted citations. This verifies the offline fallback end to end.
 */
test.describe("chat", () => {
  test("chat page renders with input and empty state", async ({ page }) => {
    await page.goto("/chat");
    await expect(
      page.getByRole("heading", { name: /ask a question/i })
    ).toBeVisible();
    await expect(
      page.getByPlaceholder(/ask a question about your documents/i)
    ).toBeVisible();
    await expect(
      page.getByText(/ask a question about your uploaded documents/i)
    ).toBeVisible();
  });

  test("falls back to demo mode and answers with citations", async ({ page }) => {
    await page.goto("/chat");

    const input = page.getByPlaceholder(/ask a question about your documents/i);
    await input.fill("What is the remote work policy?");
    await page.getByRole("button", { name: /send/i }).click();

    // Demo banner should appear once the (absent) backend fails.
    await expect(page.getByTestId("demo-banner")).toBeVisible({ timeout: 15000 });

    // The remote-work demo answer resolves citation [1].
    await expect(page.getByTestId("citation-marker-1")).toBeVisible({
      timeout: 15000,
    });
  });
});
