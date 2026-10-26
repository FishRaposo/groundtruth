import { describe, expect, it } from "vitest";
import { contextSemanticChecks, replayContextReading } from "@/lib/source-context-evidence";
import { contextObligationPlan, contextReferenceObligation } from "@/lib/source-context-references";
import cases from "../fixtures/source-context-reference-v2-parity.json";

describe("canonical typed-reference parser and obligation projections", () => {
  // Defect: JS replay could drift in any typed slot/reference/guard/domain or Python Unicode predicate/range.
  it.each(cases)("$name", c => {
    const reading = replayContextReading(c.body, c.operation, c.state, c.sha256, "scoped_note_context_v2");
    expect(reading).toEqual(c.reading);
    if (reading) {
      const checks = contextSemanticChecks(reading);
      expect(checks).toEqual(c.semantic_checks);
      expect(contextObligationPlan(reading, checks)).toEqual(c.obligation_plan);
      expect(contextReferenceObligation(reading)).toEqual(c.reference_obligation);
      expect(checks.some(check => check.name === "card_reference_identity")).toBe(false);
    }
  });
});
