import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { installOfflineNetworkGuard } from "./offlineNetworkGuard";

test("offline recruiter journey, all routes, reset and keyboard evidence", async ({
  page,
  baseURL,
}, info) => {
  const unexpected: string[] = [],
    errors: string[] = [];
  await page.addInitScript(() =>
    localStorage.setItem("groundtruth.source.v1", "sample"),
  );
  await page.emulateMedia({ reducedMotion: "reduce" });
  installOfflineNetworkGuard(page, baseURL, unexpected);
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
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
          `${label}-${info.project.use.viewport?.width || 1440}.png`,
        ),
        fullPage: !(await page.getByRole("dialog").isVisible()),
      });
    }
  };
  const fits = async () =>
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  const contrast = async () => {
    const failures = await page.evaluate(() => {
      const rgb = (text: string) => (text.match(/[\d.]+/g) || []).map(Number);
      const luminance = (color: number[]) =>
        color
          .slice(0, 3)
          .map((value) => {
            const channel = value / 255;
            return channel <= 0.04045
              ? channel / 12.92
              : ((channel + 0.055) / 1.055) ** 2.4;
          })
          .reduce(
            (sum, value, index) =>
              sum + value * [0.2126, 0.7152, 0.0722][index],
            0,
          );
      return Array.from(
        document.querySelectorAll<HTMLElement>(
          ".gt-badge,.gt-muted,.gt-eyebrow,.btn-primary,.gt-source-bar strong",
        ),
      )
        .filter((node) => node.offsetParent && node.textContent?.trim())
        .flatMap((node) => {
          let parent: HTMLElement | null = node;
          let background = [255, 255, 255];
          while (parent) {
            const color = rgb(getComputedStyle(parent).backgroundColor);
            if (color.length === 3 || color[3] > 0.99) {
              background = color;
              break;
            }
            parent = parent.parentElement;
          }
          const front = luminance(rgb(getComputedStyle(node).color)),
            back = luminance(background);
          const ratio =
            (Math.max(front, back) + 0.05) / (Math.min(front, back) + 0.05);
          return ratio < 4.5 ? [`${node.className}: ${ratio.toFixed(2)}`] : [];
        });
    });
    expect(failures).toEqual([]);
  };
  await page.goto("/");
  await expect(page).toHaveTitle(/GroundTruth/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "Inspect the evidence",
  );
  await expect(
    page.getByText("Interactive sample data", { exact: true }),
  ).toBeVisible();
  await fits();
  await shot("sample-overview");
  await page.getByRole("button", { name: "Start guided demo" }).click();
  await expect(page.getByLabel("Guided demo")).toContainText("1 of 6");
  const source = page.getByRole("button", {
    name: /Staging rollback runbook.*Version 2/,
  });
  await source.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("Interactive sample data", {exact: true})).toBeVisible();
  await expect(dialog).toContainText("verify the health checks");
  await expect(dialog.locator("mark")).toContainText("verify");
  await dialog.getByText("Immutable source identity").click();
  await dialog.evaluate(element => { element.scrollTop = element.scrollHeight; });
  await expect(dialog.getByText("Interactive sample data", {exact: true})).toBeInViewport();
  await dialog.evaluate(element => { element.scrollTop = 0; });
  await page.keyboard.press("Tab");
  await expect(
    dialog.getByRole("button", { name: "Close dialog" }),
  ).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(dialog.getByText("Immutable source identity")).toBeFocused();
  await expect(dialog).toContainText("Content SHA-256");
  await shot("sample-source");
  await page.keyboard.press("Escape");
  await expect(source).toBeFocused();
  await page.getByRole("button", { name: "Next step" }).click();
  await page
    .getByRole("article")
    .filter({
      has: page.getByRole("heading", {
        name: "Staging rollback runbook",
        exact: true,
      }),
    })
    .getByRole("button", { name: "Versions & evidence" })
    .click();
  await dialog
    .getByRole("button", { name: "Compare previous and current" })
    .click();
  await expect(dialog.getByLabel("Version comparison")).toContainText(
    "reopen traffic immediately",
  );
  await expect(dialog.getByLabel("Version comparison")).toContainText(
    "verify the health checks",
  );
  await shot("sample-versions");
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Next step" }).click();
  await expect(page.getByLabel("Answer and evidence")).toContainText(
    "No answer has been invented",
  );
  await page
    .locator(".gt-history")
    .getByRole("button", { name: /How do I roll back staging safely/ })
    .click();
  await expect(page.getByLabel("Answer and evidence")).toContainText(
    "verify the health checks",
  );
  await page
    .locator(".gt-history")
    .getByRole("button", { name: /What is the CEO salary/ })
    .click();
  await expect(page.getByLabel("Answer and evidence")).toContainText(
    "No answer has been invented",
  );
  await page.getByRole("button", { name: "Next step" }).click();
  await expect(page.getByLabel("Answer and evidence")).toContainText(
    "human must resolve",
  );
  await page.getByRole("button", { name: "Next step" }).click();
  await page.getByRole("button", { name: "Simulate recovery" }).click();
  await expect(page.getByRole("status")).toContainText(
    "No file parser or backend was called",
  );
  await page.getByRole("button", { name: "Next step" }).click();
  await expect(
    page.getByRole("heading", { name: "The preview is the introduction." }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Finish tour" }).click();
  await page.getByRole("link", { name: "Documents", exact: true }).click();
  await page.getByLabel("Choose documents").setInputFiles({
    name: "never-upload.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("This file must not leave the browser."),
  });
  await page.getByRole("button", { name: "Preview file selection" }).click();
  await expect(page.getByRole("status")).toContainText(
    "No file content was read or transmitted",
  );
  await page.getByRole("link", { name: "Workflows", exact: true }).click();
  await page
    .getByRole("combobox", { name: "Document", exact: true })
    .selectOption("sample-rollback");
  await page
    .getByRole("combobox", { name: "Workflow definition", exact: true })
    .selectOption("sample-review");
  await page.getByRole("button", { name: "Start review" }).click();
  await page.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(page.getByLabel("Selected workflow")).toContainText("completed");
  await expect(
    page.getByRole("button", { name: "Approve", exact: true }),
  ).toBeDisabled();
  await page.getByRole("link", { name: "Admin", exact: true }).click();
  await expect(
    page.getByText("workflow.approve", { exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Workflows", exact: true }).click();
  await page
    .getByRole("button", { name: /Runbook publication review.*completed/ })
    .click();
  await page.getByRole("button", { name: "Reset demo" }).click();
  await expect(page.getByLabel("Selected workflow")).toContainText(
    "Select or start a review",
  );
  await page.getByRole("link", { name: "Documents", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Simulate recovery" }),
  ).toBeVisible();
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
    await contrast();
    await expect(page.locator("nextjs-portal")).toHaveCount(0);
  }
  expect(unexpected).toEqual([]);
  expect(errors).toEqual([]);
});
