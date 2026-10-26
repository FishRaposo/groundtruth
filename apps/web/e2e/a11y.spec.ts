import { expect, test } from "@playwright/test";
import { AxeBuilder } from "@axe-core/playwright";
import { installOfflineNetworkGuard } from "./offlineNetworkGuard";

// WCAG 2.1 A/AA scans across the sample-rendered route surfaces. Runs in both the
// desktop, mobile, and tablet projects; sample mode must not hit the network.
const ROUTES = ["/", "/chat", "/documents", "/admin", "/workflow", "/workflows"];

for (const route of ROUTES) {
  test(`axe wcag2a/aa: ${route}`, async ({ page, baseURL }) => {
    const unexpected: string[] = [];
    await page.addInitScript(() =>
      localStorage.setItem("groundtruth.source.v1", "sample"),
    );
    await page.emulateMedia({ reducedMotion: "reduce" });
    installOfflineNetworkGuard(page, baseURL, unexpected);
    await page.goto(route);
    await expect(page).toHaveTitle(/GroundTruth/);
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(
      results.violations.map((violation) => violation.id),
      `${route} axe violations`,
    ).toEqual([]);
    expect(unexpected, `external requests on ${route}`).toEqual([]);
  });
}
