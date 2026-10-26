import { defineConfig } from "@playwright/test";
import live from "./playwright.live.config";

// Explicit acceptance profile: cached reader + NLI models are required.
// Ordinary credential-free lexical CI keeps its existing live-suite selector.
export default defineConfig({
  ...live,
  testMatch: ["combined-procedure.spec.ts"],
});
