import { describe, expect, it } from "vitest";
import {
  createSampleState,
  sampleQuestion,
  recoverSample,
  restoreSample,
  CURRENT_HASH,
  CURRENT_PASSAGE,
  OLD_HASH,
  OLD_PASSAGE,
} from "@/lib/portfolioSample";
import { createHash } from "node:crypto";

describe("coherent sample scenarios", () => {
  it("does not reuse a retained query identity after a guided reset/replacement", () => {
    const initial = createSampleState();
    const guided = sampleQuestion("How do I roll back staging?", initial);
    const next = sampleQuestion("What is the CEO salary?", {
      ...initial,
      queries: [guided],
    });
    expect(next.id).not.toBe(guided.id);
  });
  it("hashes the exact saved synthetic passage", () => {
    expect(createHash("sha256").update(CURRENT_PASSAGE).digest("hex")).toBe(
      CURRENT_HASH,
    );
    expect(createHash("sha256").update(OLD_PASSAGE).digest("hex")).toBe(
      OLD_HASH,
    );
  });
  it("starts populated and resets recovery and version changes together", () => {
    const initial = createSampleState();
    const recovered = recoverSample(initial);
    expect(
      recovered.documents.filter((d) => d.status === "error"),
    ).toHaveLength(0);
    const restored = restoreSample(recovered, "sample-rollback", 1);
    expect(restored.documents[0].version_number).toBe(3);
    expect(createSampleState()).toEqual(initial);
    expect(initial.documents.filter((d) => d.status === "error")).toHaveLength(
      1,
    );
  });
  it("binds current rollback evidence and refuses missing or conflicting facts", () => {
    const state = createSampleState();
    const query = sampleQuestion("How do I roll back staging?", state);
    expect(query.sources[0].document_version).toBe(2);
    expect(query.sources[0].content_hash).toMatch(/^[a-f0-9]{64}$/);
    expect(query.sources[0].quoted_text).toContain("verify");
    expect(
      sampleQuestion("What is the salary of the CEO?", state).refused,
    ).toBe(true);
    expect(
      sampleQuestion("Which conflicting database procedure applies?", state)
        .outcome,
    ).toBe("refused");
  });
});
