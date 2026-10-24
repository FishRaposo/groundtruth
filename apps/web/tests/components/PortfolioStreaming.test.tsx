import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import PortfolioChat from "@/components/PortfolioChat";

const { p } = vi.hoisted(() => ({
  p: {
    source: "connected",
    ready: true,
    epoch: 0,
    key: "unit-only-key",
    conversation: "",
    selectedQuery: null,
    documents: [],
    history: [],
    conversations: [],
    error: null,
    loading: false,
    runtime: null,
    sample: { queries: [] },
    client: { request: vi.fn() },
    setSelectedQuery: vi.fn(),
    setSample: vi.fn(),
    setSource: vi.fn(),
    setConversation: vi.fn(),
    refresh: vi.fn().mockResolvedValue(undefined),
  },
}));
vi.mock("@/components/PortfolioProvider", () => ({
  API_URL: "http://127.0.0.1:8400",
  usePortfolio: () => p,
}));
describe("persisted streaming outcomes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.history.replaceState(null, "", "/chat");
  });
  afterEach(() => vi.unstubAllGlobals());
  it("accepts a persisted refused event as the terminal outcome without requiring done", async () => {
    const refusal = {
      type: "refused",
      id: "query-refusal",
      question: "What is the CEO salary?",
      answer: null,
      sources: [],
      refused: true,
      outcome: "refused",
      refusal_reason: "No authorized evidence",
      evidence_access: "available",
      retrieval_trace: null,
      confidence: 0,
      token_usage: null,
      created_at: "2026-10-24T03:00:00Z",
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        body: new ReadableStream({
          start(controller) {
            controller.enqueue(
              new TextEncoder().encode(`data: ${JSON.stringify(refusal)}\n\n`),
            );
            controller.close();
          },
        }),
      }),
    );
    render(<PortfolioChat />);
    fireEvent.click(screen.getByLabelText("Stream the actual answer (SSE)"));
    fireEvent.change(screen.getByLabelText("What do you need to know?"), {
      target: { value: refusal.question },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));
    await waitFor(() =>
      expect(p.setSelectedQuery).toHaveBeenCalledWith(
        expect.objectContaining({
          id: refusal.id,
          outcome: "refused",
          refused: true,
        }),
      ),
    );
    expect(window.location.search).toBe("?query=query-refusal");
  });
});
