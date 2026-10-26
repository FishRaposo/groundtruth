import { describe, expect, it } from "vitest";
import { contextSemanticChecks, replayContextReading } from "@/lib/source-context-evidence";
import cases from "../fixtures/source-context-parser-v319.json";

describe("Python-generated contextual grammar parity", () => {
  // Defect: ASCII JS words, UTF-16 offsets, BOM whitespace or a partial body can diverge from the authority.
  it.each(cases)("reconstructs complete Python result: $name", ({ body, operation, state, sha256, reading, semantic_checks }) => {
    const replayed = replayContextReading(body, operation, state, sha256);
    expect(replayed).toEqual(reading);
    if (replayed) expect(contextSemanticChecks(replayed)).toEqual(semantic_checks);
  });
});
