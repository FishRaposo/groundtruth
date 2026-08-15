import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";

export default defineConfig([
  ...nextVitals,
  {
    rules: {
      // Initial data loading is intentionally effect-driven; the calls update state
      // asynchronously after API responses, not during render.
      "react-hooks/set-state-in-effect": "off",
    },
  },
  globalIgnores([".next/**", "playwright-report/**", "test-results/**"]),
]);
