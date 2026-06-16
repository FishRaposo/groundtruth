import { describe, it, expect } from "vitest";
import {
  getDemoResponse,
  streamDemoResponse,
  buildDemoQueryResponse,
  isNetworkError,
  DEMO_NOTICE,
} from "@/lib/demoMode";
import type { StreamEvent } from "@/types";

describe("demoMode.getDemoResponse", () => {
  it("answers remote-work questions with grounded sources", () => {
    const r = getDemoResponse("What is the remote work policy?");
    expect(r.refused).toBe(false);
    expect(r.sources.length).toBeGreaterThan(0);
    expect(r.answer).toContain("[1]");
  });

  it("answers security questions", () => {
    const r = getDemoResponse("How does access authentication work?");
    expect(r.refused).toBe(false);
    expect(r.sources[0].document_title).toBe("Security Handbook");
  });

  it("refuses unknown questions", () => {
    const r = getDemoResponse("What is the capital of Mars?");
    expect(r.refused).toBe(true);
    expect(r.sources).toEqual([]);
  });
});

describe("demoMode.streamDemoResponse", () => {
  it("streams tokens then citations then done for a known question", async () => {
    const events: StreamEvent[] = [];
    for await (const e of streamDemoResponse("remote work policy")) {
      events.push(e);
    }
    expect(events.some((e) => e.type === "token")).toBe(true);
    expect(events.some((e) => e.type === "citations")).toBe(true);
    expect(events[events.length - 1].type).toBe("done");
  });

  it("streams a refusal for an unknown question", async () => {
    const events: StreamEvent[] = [];
    for await (const e of streamDemoResponse("unknown topic xyz")) {
      events.push(e);
    }
    expect(events.some((e) => e.type === "refused")).toBe(true);
  });
});

describe("demoMode.buildDemoQueryResponse", () => {
  it("returns an answer for known questions", () => {
    const resp = buildDemoQueryResponse("remote work");
    expect(resp.refused).toBe(false);
    expect(resp.answer).not.toBeNull();
  });

  it("returns refused with null answer for unknown questions", () => {
    const resp = buildDemoQueryResponse("nonsense query zzz");
    expect(resp.refused).toBe(true);
    expect(resp.answer).toBeNull();
  });
});

describe("demoMode.isNetworkError", () => {
  it("treats TypeError as a network error", () => {
    expect(isNetworkError(new TypeError("Failed to fetch"))).toBe(true);
  });

  it("treats fetch-failure messages as network errors", () => {
    expect(isNetworkError(new Error("fetch failed"))).toBe(true);
    expect(isNetworkError(new Error("Network connection lost"))).toBe(true);
  });

  it("does not treat application errors as network errors", () => {
    expect(isNetworkError(new Error("Query not found"))).toBe(false);
  });

  it("handles non-error values", () => {
    expect(isNetworkError("oops")).toBe(false);
    expect(isNetworkError(null)).toBe(false);
  });
});

describe("demoMode constants", () => {
  it("exposes a demo notice", () => {
    expect(DEMO_NOTICE).toMatch(/demo mode/i);
  });
});
