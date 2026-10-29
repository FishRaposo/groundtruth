import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import PortfolioChat from "@/components/PortfolioChat";

const { p } = vi.hoisted(() => ({ p: {
  source: "connected", ready: true, epoch: 0, key: "unit-alpha", conversation: "",
  selectedQuery: null, documents: [], history: [], conversations: [], error: null,
  loading: false, runtime: null, sample: { queries: [] },
  client: { request: vi.fn() }, setSelectedQuery: vi.fn(), setSample: vi.fn(),
  setSource: vi.fn(), setConversation: vi.fn(), refresh: vi.fn().mockResolvedValue(undefined),
} }));
vi.mock("@/components/PortfolioProvider", () => ({
  API_URL: "http://127.0.0.1:8402", usePortfolio: () => p,
}));
const saved = { id: "old-private-query", question: "Private question", answer: "Private answer", sources: [], refused: false, outcome: "completed" };

describe("connected chat request lifecycle", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    p.key = "unit-alpha"; p.epoch = 0; p.conversation = "";
    p.client = { request: vi.fn() };
    p.refresh.mockResolvedValue(undefined);
    window.history.replaceState(null, "", "/chat");
  });
  afterEach(() => vi.unstubAllGlobals());

  it("retries the failed saved-answer read instead of only refreshing shared state", async () => {
    window.history.replaceState(null, "", `/chat?query=${saved.id}`);
    const fetch = vi.fn()
      .mockRejectedValueOnce(new TypeError("Temporary saved-answer outage"))
      .mockResolvedValue({ ok: true, status: 200, json: async () => saved });
    vi.stubGlobal("fetch", fetch);
    render(<PortfolioChat />);
    expect(await screen.findByText("Temporary saved-answer outage")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(String(fetch.mock.calls[1][0])).toContain(`/api/queries/${saved.id}`);
    await waitFor(() => expect(p.setSelectedQuery).toHaveBeenCalledWith(saved));
    expect(screen.queryByText("Temporary saved-answer outage")).not.toBeInTheDocument();
  });

  it.each(["refused", "done"])("retracts provisional tokens immediately on %s before history refresh settles", async (type) => {
    let controller!: ReadableStreamDefaultController<Uint8Array>;
    let finishRefresh!: () => void;
    p.refresh.mockReturnValue(new Promise<void>((resolve) => { finishRefresh = resolve; }));
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, body: new ReadableStream<Uint8Array>({ start(value) { controller = value; } }) }));
    render(<PortfolioChat />);
    fireEvent.click(screen.getByLabelText("Stream the actual answer (SSE)"));
    fireEvent.change(screen.getByLabelText("What do you need to know?"), { target: { value: "Current question" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));
    await waitFor(() => expect(controller).toBeDefined());
    try {
      await act(async () => { controller.enqueue(new TextEncoder().encode('data: {"type":"token","content":"UNSUPPORTED_PARTIAL"}\n\n')); });
      expect(await screen.findByText("UNSUPPORTED_PARTIAL")).toBeVisible();
      const terminal = { type, id: "refused-query", question: "Current question", answer: null, sources: [], refused: true, outcome: "refused", refusal_reason: "Source changed" };
      await act(async () => { controller.enqueue(new TextEncoder().encode(`data: ${JSON.stringify(terminal)}\n\n`)); });
      await waitFor(() => expect(p.setSelectedQuery).toHaveBeenCalledWith(expect.objectContaining({ id: "refused-query", answer: null, refused: true })));
      expect(p.refresh).toHaveBeenCalled();
      expect(screen.queryByText("UNSUPPORTED_PARTIAL")).not.toBeInTheDocument();
    } finally {
      await act(async () => { finishRefresh(); });
    }
  });

  it("waits for a new conversation before permitting a question, retaining its draft", async () => {
    let finish!: (value: unknown) => void;
    p.client.request.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    render(<PortfolioChat />);
    const create = screen.getByRole("button", { name: "New conversation" });
    fireEvent.click(create);
    fireEvent.change(screen.getByLabelText("What do you need to know?"), { target: { value: "Keep this draft" } });
    expect(screen.getByRole("button", { name: /Ask question/ })).toBeDisabled();
    fireEvent.click(create);
    expect(p.client.request).toHaveBeenCalledTimes(1);
    await act(async () => { finish({ id: "new-conversation" }); });
    expect(p.setConversation).toHaveBeenCalledWith("new-conversation");
    expect(screen.getByLabelText("What do you need to know?")).toHaveValue("Keep this draft");
    expect(screen.getByRole("button", { name: /Ask question/ })).toBeEnabled();
  });

  it("cancels an old identity's request and ignores its late response", async () => {
    let finish!: (value: unknown) => void;
    let signal!: AbortSignal;
    vi.stubGlobal("fetch", vi.fn().mockImplementation((_url, options) => {
      signal = options.signal;
      return new Promise((resolve) => { finish = resolve; });
    }));
    const view = render(<PortfolioChat />);
    fireEvent.change(screen.getByLabelText("What do you need to know?"), { target: { value: saved.question } });
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));
    await waitFor(() => expect(signal).toBeDefined());
    p.key = "unit-beta"; p.epoch = 1; p.client = { request: vi.fn() };
    view.rerender(<PortfolioChat />);
    expect(signal.aborted).toBe(true);
    await act(async () => { finish({ ok: true, status: 200, json: async () => saved }); });
    expect(p.setSelectedQuery).not.toHaveBeenCalled();
    expect(window.location.search).not.toContain(saved.id);
  });

  it("ignores conversation creation completed after a context switch", async () => {
    let finish!: (value: unknown) => void;
    p.client.request.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    const view = render(<PortfolioChat />);
    fireEvent.click(screen.getByRole("button", { name: "New conversation" }));
    p.key = "unit-beta"; p.epoch = 1; p.client = { request: vi.fn() };
    view.rerender(<PortfolioChat />);
    await act(async () => { finish({ id: "old-private-conversation" }); });
    expect(p.setConversation).not.toHaveBeenCalled();
  });
  it("does not render late private stream events after an identity switch", async () => {
    let controller!: ReadableStreamDefaultController;
    let signal!: AbortSignal;
    vi.stubGlobal("fetch", vi.fn().mockImplementation((_url, options) => {
      signal = options.signal;
      return Promise.resolve({ ok: true, status: 200, body: new ReadableStream({ start(value) { controller = value; } }) });
    }));
    const view = render(<PortfolioChat />);
    fireEvent.click(screen.getByLabelText("Stream the actual answer (SSE)"));
    fireEvent.change(screen.getByLabelText("What do you need to know?"), { target: { value: saved.question } });
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));
    await waitFor(() => expect(controller).toBeDefined());
    p.key = "unit-beta"; p.epoch = 1; p.client = { request: vi.fn() };
    view.rerender(<PortfolioChat />);
    expect(signal.aborted).toBe(true);
    await act(async () => {
      controller.enqueue(new TextEncoder().encode('data: {"type":"token","content":"private streamed content"}\n\n'));
      controller.enqueue(new TextEncoder().encode(`data: ${JSON.stringify({ type: "done", ...saved })}\n\n`));
      controller.close();
    });
    expect(screen.queryByText("private streamed content")).not.toBeInTheDocument();
    expect(p.setSelectedQuery).not.toHaveBeenCalled();
  });
  it("can submit again after cancellation without old cleanup aborting the new request", async () => {
    const pending: { finish: (value: unknown) => void; signal: AbortSignal }[] = [];
    vi.stubGlobal("fetch", vi.fn().mockImplementation((_url, options) => new Promise((resolve) => {
      pending.push({ finish: resolve, signal: options.signal });
    })));
    render(<PortfolioChat />);
    fireEvent.change(screen.getByLabelText("What do you need to know?"), { target: { value: saved.question } });
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));
    await waitFor(() => expect(pending).toHaveLength(1));
    fireEvent.click(screen.getByRole("button", { name: "Cancel request" }));
    expect(pending[0].signal.aborted).toBe(true);
    expect(screen.getByRole("button", { name: "Ask question" })).toBeEnabled();
    fireEvent.change(screen.getByLabelText("What do you need to know?"), { target: { value: "New request" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));
    await waitFor(() => expect(pending).toHaveLength(2));
    await act(async () => { pending[0].finish({ ok: true, status: 200, json: async () => saved }); });
    expect(pending[1].signal.aborted).toBe(false);
    expect(screen.getByRole("button", { name: /Retrieving evidence/ })).toBeDisabled();
    expect(p.setSelectedQuery).not.toHaveBeenCalled();
    const current = { ...saved, id: "new-query", question: "New request" };
    await act(async () => { pending[1].finish({ ok: true, status: 200, json: async () => current }); });
    expect(p.setSelectedQuery).toHaveBeenCalledWith(current);
    expect(window.location.search).toBe("?query=new-query");
  });
});
