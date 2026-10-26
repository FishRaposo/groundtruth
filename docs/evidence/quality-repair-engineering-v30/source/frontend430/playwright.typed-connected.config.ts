import { defineConfig } from "@playwright/test";
import live from "./playwright.live.config";

// Root owns the already running production services and private disposable DB.
// No implicit server, retry, recording or sample-mode fallback is permitted.
export default defineConfig({
  ...live,
  testMatch: ["typed-reference-connected.spec.ts"],
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 300000,
  webServer: undefined,
  outputDir: process.env.GROUNDTRUTH_TYPED_RESULTS ?? "test-results/typed-connected-v364",
  use: { ...live.use, baseURL: "http://127.0.0.1:3506", trace: "off", screenshot: "off", video: "off" },
});
