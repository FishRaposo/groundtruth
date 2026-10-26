import { defineConfig } from "@playwright/test";
import live from "./playwright.live.config";

// Supplemental UI evidence only; never replaces the unchanged acceptance suite.
export default defineConfig({
  ...live,
  testMatch: "coverage-diagnostic.spec.ts",
});
