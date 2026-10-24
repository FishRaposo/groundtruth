import { expect, test } from "@playwright/test";
import { AxeBuilder } from "@axe-core/playwright";

// WCAG 2.1 A/AA scans across the sample-rendered route surfaces. Runs in both the
// chromium and mobile-chromium projects; sample mode must not hit the network.
const ROUTES = ["/", "/chat", "/documents", "/admin", "/workflow", "/workflows"];
const DENSE = new Set(["/chat", "/documents"]);

for (const route of ROUTES) {
  test(`axe wcag2a/aa: ${route}`, async ({ page }, info) => {
    const width = info.project.use.viewport?.width ?? 1440;
    if (width < 1440 && !DENSE.has(route)) return;
    const unexpected: string[] = [];
    await page.addInitScript(() =>
      localStorage.setItem("groundtruth.source.v1", "sample"),
    );
    await page.emulateMedia({ reducedMotion: "reduce" });
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (
        url.pathname.startsWith("/api/") ||
        !["localhost", "127.0.0.1"].includes(url.hostname)
      )
        unexpected.push(`${request.method()} ${url.origin}${url.pathname}`);
    });
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
