import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { StrictMode } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import PortfolioProvider, { usePortfolio } from "@/components/PortfolioProvider";
import PortfolioChat, { SourceDrawer } from "@/components/PortfolioChat";
import type { QueryResponse, SourceCitation } from "@/types";

const citation = (index: number): SourceCitation => ({
  citation_index: index, document_title: `Document ${index}`,
  chunk_id: `chunk-${index}`, document_id: `doc-${index}`,
  content_preview: `Source ${index}`, quoted_text: `Quote ${index}`, relevance_score: 1,
});
const saved = (id = "saved-a"): QueryResponse => ({
  id, question: `Question ${id}`, answer: `Answer ${id}`, sources: [citation(1), citation(2)],
  refused: false, outcome: "completed", confidence: null, token_usage: null,
  retrieval_trace: null, created_at: "2026-10-24T00:00:00Z",
});
const history = [saved(), saved("saved-b")].map(({ id, question, refused, confidence, created_at, outcome }) =>
  ({ id, question, refused, confidence, created_at, outcome }));
const response = (payload: unknown, ok = true) => ({
  ok, status: ok ? 200 : 403, json: async () => payload,
});
function defaults(url: string) {
  return url.includes("/documents") ? { documents: [] }
    : url.includes("/queries?") ? { queries: history }
      : url.includes("/conversations") ? [{ id: "conversation-kept", title: "Kept" }]
        : url.includes("/identity") ? { id: "operator", name: "Operator", workspace_id: "ops", is_admin: false }
          : { status: "ok" };
}
interface Pending {
  url: string;
  signal: AbortSignal;
  finish: (value: ReturnType<typeof response>) => void;
}
function deferFetch(matches: (url: string, options: RequestInit) => boolean) {
  const pending: Pending[] = [];
  vi.stubGlobal("fetch", vi.fn((input: string, options: RequestInit) => {
    const url = String(input);
    return matches(url, options)
      ? new Promise<ReturnType<typeof response>>(finish => pending.push({ url, signal: options.signal!, finish }))
      : Promise.resolve(response(defaults(url)));
  }));
  return pending;
}
function Controls({ chat = false }: { chat?: boolean }) {
  const p = usePortfolio();
  return <>
    <button onClick={() => void p.refresh()}>Refresh state</button>
    <button onClick={() => p.connect("beta")}>Change identity</button>
    <button onClick={() => p.setConversation("conversation-kept")}>Change session</button>
    <button onClick={() => p.setSelectedQuery(saved())}>Select answer</button>
    <button onClick={() => void p.client.request("/api/background").catch(() => undefined)}>Background read</button>
    <output data-testid="history">{p.history.map(q => q.question).join(",")}</output>
    <output data-testid="loading">{String(p.loading)}</output>
    {chat ? <PortfolioChat /> : null}
  </>;
}
async function connected(chat = false) {
  const view = render(<PortfolioProvider><Controls chat={chat} /></PortfolioProvider>);
  await waitFor(() => expect(screen.getByTestId("loading")).toHaveTextContent("true"));
  return view;
}
beforeEach(() => {
  localStorage.clear(); sessionStorage.clear();
  localStorage.setItem("groundtruth.source.v1", "connected");
  sessionStorage.setItem("groundtruth.api-key.v1", "alpha");
  window.history.replaceState(null, "", "/chat");
});
afterEach(() => vi.unstubAllGlobals());

describe("provider request ownership", () => {
  it("aborts the older refresh and keeps newer history when old JSON arrives last", async () => {
    const pending = deferFetch(url => url.includes("/queries?"));
    await connected();
    await waitFor(() => expect(pending).toHaveLength(1));
    fireEvent.click(screen.getByText("Refresh state"));
    await waitFor(() => expect(pending).toHaveLength(2));
    expect(pending[0].signal.aborted).toBe(true);
    await act(async () => pending[1].finish(response({ queries: [{ ...history[0], question: "New history" }] })));
    await act(async () => pending[0].finish(response({ queries: [{ ...history[0], question: "Old history" }] })));
    expect(screen.getByTestId("history")).toHaveTextContent("New history");
    expect(screen.getByTestId("history")).not.toHaveTextContent("Old history");
  });
  it("does not let an old refresh finally clear a newer refresh's loading state", async () => {
    const pending = deferFetch(url => url.includes("/queries?"));
    await connected();
    fireEvent.click(screen.getByText("Refresh state"));
    await waitFor(() => expect(pending).toHaveLength(2));
    await act(async () => pending[0].finish(response({ queries: [] })));
    expect(screen.getByTestId("loading")).toHaveTextContent("true");
    await act(async () => pending[1].finish(response({ queries: [] })));
    expect(screen.getByTestId("loading")).toHaveTextContent("false");
  });
  it("aborts pending provider requests when unmounted", async () => {
    const pending = deferFetch(() => true);
    const view = await connected();
    await waitFor(() => expect(pending).toHaveLength(5));
    view.unmount();
    expect(pending.every(item => item.signal.aborted)).toBe(true);
  });
});

describe("chat operation ownership", () => {
  it("keeps shared reads independent of inspections and effect replay, then aborts them on unmount", async () => {
    sessionStorage.removeItem("groundtruth.api-key.v1");
    const pending = deferFetch(url => url.endsWith("/api/background") || url.includes("/sources/"));
    const view = render(<StrictMode><PortfolioProvider><Controls chat /></PortfolioProvider></StrictMode>);
    await screen.findByRole("button", { name: "New conversation" });
    fireEvent.click(screen.getByText("Background read"));
    await waitFor(() => expect(pending).toHaveLength(1));
    fireEvent.click(screen.getByText("Select answer"));
    fireEvent.click(screen.getByRole("button", { name: /Document 1/ }));
    fireEvent.click(screen.getByRole("button", { name: /Document 2/ }));
    expect(pending[0].signal.aborted).toBe(false);
    expect(pending[1].signal.aborted).toBe(true);
    await act(async () => pending[1].finish(response(citation(1))));
    expect(pending[2].signal.aborted).toBe(false);
    await act(async () => pending[2].finish(response(citation(2))));
    view.unmount();
    await waitFor(() => expect(pending[0].signal.aborted).toBe(true));
    pending[0].finish(response({ status: "ok" }));
  });
  it.each(["success", "error"])("keeps the later inspected source after an older %s", async outcome => {
    const pending = deferFetch(url => url.includes("/sources/"));
    render(<PortfolioProvider><Controls chat /></PortfolioProvider>);
    fireEvent.click(screen.getByText("Select answer"));
    fireEvent.click(await screen.findByRole("button", { name: /Document 1/ }));
    fireEvent.click(screen.getByRole("button", { name: /Document 2/ }));
    await waitFor(() => expect(pending).toHaveLength(2));
    expect(pending[0].signal.aborted).toBe(true);
    await act(async () => pending[1].finish(response(citation(2))));
    await act(async () => pending[0].finish(outcome === "success"
      ? response(citation(1)) : response({ detail: "Obsolete inspection error" }, false)));
    expect(screen.getByRole("dialog")).toHaveTextContent("Source 2: Document 2");
    expect(screen.queryByText("Obsolete inspection error")).not.toBeInTheDocument();
  });
  it("does not let old inspection cleanup abort the newer inspection", async () => {
    const pending = deferFetch(url => url.includes("/sources/"));
    render(<PortfolioProvider><Controls chat /></PortfolioProvider>);
    fireEvent.click(screen.getByText("Select answer"));
    fireEvent.click(await screen.findByRole("button", { name: /Document 1/ }));
    fireEvent.click(screen.getByRole("button", { name: /Document 2/ }));
    await act(async () => pending[0].finish(response(citation(1))));
    expect(pending[1].signal.aborted).toBe(false);
    await act(async () => pending[1].finish(response(citation(2))));
    expect(screen.getByRole("dialog")).toHaveTextContent("Source 2: Document 2");
  });
  it.each(["Change identity", "Change session"])("aborts an inspection on %s", async action => {
    const pending = deferFetch(url => url.includes("/sources/"));
    render(<PortfolioProvider><Controls chat /></PortfolioProvider>);
    fireEvent.click(screen.getByText("Select answer"));
    fireEvent.click(await screen.findByRole("button", { name: /Document 1/ }));
    fireEvent.click(screen.getByText(action));
    expect(pending[0].signal.aborted).toBe(true);
    await act(async () => pending[0].finish(response(citation(1))));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
  it("aborts obsolete inspection when a new question starts", async () => {
    const pending = deferFetch((url, options) => url.includes("/sources/") || options.method === "POST");
    render(<PortfolioProvider><Controls chat /></PortfolioProvider>);
    fireEvent.click(screen.getByText("Select answer"));
    fireEvent.click(await screen.findByRole("button", { name: /Document 1/ }));
    fireEvent.change(screen.getByLabelText("What do you need to know?"), { target: { value: "New question" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));
    expect(pending[0].signal.aborted).toBe(true);
    await act(async () => pending[0].finish(response({ detail: "Obsolete inspection error" }, false)));
    expect(screen.queryByText("Obsolete inspection error")).not.toBeInTheDocument();
    await act(async () => pending[1].finish(response(saved("new-query"))));
    expect(screen.getByText("Answer new-query")).toBeInTheDocument();
  });
  it("aborts a cancelled saved-query load without old cleanup aborting the next load", async () => {
    const pending = deferFetch(url => /\/api\/queries\/saved-[ab]$/.test(url));
    render(<PortfolioProvider><Controls chat /></PortfolioProvider>);
    fireEvent.click(await screen.findByRole("button", { name: /Question saved-a/ }));
    await waitFor(() => expect(pending).toHaveLength(1));
    fireEvent.click(screen.getByRole("button", { name: "Cancel request" }));
    expect(pending[0].signal.aborted).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: /Question saved-b/ }));
    await waitFor(() => expect(pending).toHaveLength(2));
    await act(async () => pending[0].finish(response(saved())));
    expect(pending[1].signal.aborted).toBe(false);
    expect(screen.getByRole("button", { name: /Retrieving evidence/ })).toBeDisabled();
    await act(async () => pending[1].finish(response(saved("saved-b"))));
    expect(screen.getByText("Answer saved-b")).toBeInTheDocument();
    expect(window.location.search).toBe("?query=saved-b");
  });
  it("restores the selected conversation and saved query on a fresh mount", async () => {
    sessionStorage.setItem("groundtruth.conversation.v1", "conversation-kept");
    window.history.replaceState(null, "", "/chat?query=saved-a");
    const pending = deferFetch(url => url.endsWith("/api/queries/saved-a"));
    render(<PortfolioProvider><Controls chat /></PortfolioProvider>);
    await waitFor(() => expect(pending).toHaveLength(1));
    await act(async () => pending[0].finish(response({ ...saved(), conversation_id: "conversation-kept" })));
    expect(screen.getByText("Answer saved-a")).toBeInTheDocument();
    expect(screen.getByLabelText("Conversation")).toHaveValue("conversation-kept");
    expect(sessionStorage.getItem("groundtruth.conversation.v1")).toBe("conversation-kept");
    expect(window.location.search).toBe("?query=saved-a");
  });
});

it("renders corrupt recorded spans without marking the canonical quote", () => {
  render(<SourceDrawer source={{ ...citation(1), answer_spans: [{ start: 0, end: 1, text: "wrong" }] }} close={vi.fn()} />);
  expect(screen.getByLabelText("Canonical quoted evidence")).toHaveTextContent("Quote 1");
  expect(screen.getByLabelText("Canonical quoted evidence").querySelector("mark")).toBeNull();
  expect(screen.getByText(/no answer span highlight is shown/)).toBeInTheDocument();
});
