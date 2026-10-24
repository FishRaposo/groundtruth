import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import PortfolioChat, { SourceDrawer } from "@/components/PortfolioChat";
import { RuntimeSummary } from "@/components/PortfolioShell";
import type { QueryResponse, SourceCitation } from "@/types";

const { p } = vi.hoisted(() => ({ p: {
  source: "connected", ready: true, epoch: 0, key: "", conversation: "",
  selectedQuery: null as QueryResponse | null, documents: [], history: [],
  conversations: [], error: null, loading: false, runtime: null as Record<string, unknown> | null,
  sample: { queries: [] }, client: { request: vi.fn() }, setSelectedQuery: vi.fn(),
  setSample: vi.fn(), setSource: vi.fn(), setConversation: vi.fn(), refresh: vi.fn(),
} }));
vi.mock("@/components/PortfolioProvider", () => ({
  API_URL: "http://127.0.0.1:8402", usePortfolio: () => p,
}));
const quote = "🧭 First pause. Restore ✅ snapshot. Then verify.";
const selected = "Restore ✅ snapshot.";
const start = Array.from(quote.split(selected)[0]).length;
const source = {
  chunk_id: "chunk", document_id: "doc", document_title: "Canonical runbook",
  citation_index: 1, relevance_score: 0.7, content_preview: "Truncated preview",
  quoted_text: quote, content: "Extra context must not replace the canonical quote.",
  answer_spans: [{ start, end: start + Array.from(selected).length, text: selected }],
};
const query: QueryResponse = {
  id: "query", question: "How to restore?", answer: selected, sources: [],
  refused: false, outcome: "completed", confidence: null, token_usage: null,
  retrieval_trace: null, created_at: "2026-10-24T00:00:00Z",
  provenance: { answer_selection: {
    mode: "reader", contract: "reader-span-v1", model: "local-reader", revision: "pinned-revision",
    threshold: -4, decision: "answered", score: 7.3,
  } },
};
beforeEach(() => { p.selectedQuery = null; p.runtime = null; window.history.replaceState(null, "", "/chat"); });
describe("actual reader evidence", () => {
  it("highlights exact Unicode codepoint spans inside the whole canonical quote", () => {
    render(<SourceDrawer source={source} close={vi.fn()} />);
    expect(screen.getByLabelText("Canonical quoted evidence")).toHaveTextContent(quote);
    expect(screen.getByText(selected, { selector: "mark" })).toHaveAttribute("data-answer-span", "true");
    expect(screen.getByText(/Offsets use Unicode codepoints/)).toBeVisible();
  });
  it("rejects corrupt spans without losing the canonical source text", () => {
    render(<SourceDrawer source={{ ...source, answer_spans: [{ start: 0, end: 2, text: selected }] } as SourceCitation} close={vi.fn()} />);
    expect(screen.getByLabelText("Canonical quoted evidence")).toHaveTextContent(quote);
    expect(document.querySelector("mark[data-answer-span]")).toBeNull();
    expect(screen.getByText(/Saved answer spans could not be verified/)).toBeVisible();
  });
  it("keeps historical span metadata unknown and never treats a preview as canonical", () => {
    render(<SourceDrawer source={{ ...source, quoted_text: null, answer_spans: undefined } as SourceCitation} close={vi.fn()} />);
    expect(screen.getByText(/Canonical quote unavailable/)).toBeVisible();
    expect(screen.getByText(/Answer span metadata unknown/)).toBeVisible();
    expect(document.querySelector("mark[data-answer-span]")).toBeNull();
  });
  it("shows recorded selector identity and decision without claiming calibrated probability", () => {
    p.selectedQuery = query;
    render(<PortfolioChat />);
    const evidence = screen.getByLabelText("Answer selection evidence");
    expect(evidence).toHaveTextContent("Local extractive reader");
    expect(evidence).toHaveTextContent("local-reader");
    expect(evidence).toHaveTextContent("pinned-revision");
    expect(evidence).toHaveTextContent("answered");
    expect(evidence).toHaveTextContent("not calibrated probabilities");
  });
  it("shows a saved reader error as a failure, separate from refusal", () => {
    p.selectedQuery = { ...query, outcome: "error", answer: null, provenance: { answer_selection: { mode: "reader", decision: "error" } } };
    render(<PortfolioChat />);
    expect(screen.getByLabelText("Answer and evidence")).toHaveTextContent("Reader failed");
    expect(screen.getByText(/This is an execution failure/)).toBeVisible();
    expect(document.querySelector(".gt-refusal")).toBeNull();
  });
  it("shows API-reported reader readiness and leaves omitted identity unknown", () => {
    p.runtime = { runtime: { answer_selection: { mode: "reader", ready: false } } };
    render(<RuntimeSummary />);
    expect(screen.getByText(/Local extractive reader · not ready/)).toBeVisible();
    expect(screen.getByText(/Reader model: unknown/)).toBeVisible();
  });
  it.each(["not_loaded", "ready", "error", "disabled"])("preserves API reader readiness %s", (readiness) => {
    p.runtime = { runtime: { answer_selection: { mode: "reader", readiness } } };
    render(<RuntimeSummary />);
    expect(screen.getByText(`Local extractive reader · ${readiness}`)).toBeVisible();
  });
});
